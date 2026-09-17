import asyncio
from datetime import datetime
import json
import os
import re
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from discord_webhook import DiscordWebhook, DiscordEmbed
import config

try:
    import rclone
except ImportError:
    rclone = None

try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False


# Rclone Configuration
rcloneConfig = getattr(config, "rcloneConfig", """
[remote]
type = REPLACE
scope = ALL
token = THIS
""")
rcloneRemotePath = getattr(config, "rcloneRemotePath", "remote:JoystickVODS/")
checkTimeout = getattr(config, "joystick_check_timeout", 120)


def get_request_headers(include_auth=False):
    """Build request headers with User-Agent and Cookie from config."""
    headers = dict(getattr(config, "joystick_headers", {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
        "Referer": "https://joystick.tv/",
    }))
    
    cookie_str = getattr(config, "joystick_cookie_str", "").strip()
    if cookie_str:
        headers["Cookie"] = cookie_str
        
    api_key = getattr(config, "joystick_api_key", "").strip()
    if api_key and include_auth:
        token = api_key if api_key.lower().startswith("bearer ") else f"Bearer {api_key}"
        headers["Authorization"] = token
        
    return headers


async def fetch_page(url):
    """Fetch URL using curl_cffi or aiohttp."""
    headers = get_request_headers(include_auth=False)

    if CURL_CFFI_AVAILABLE:
        try:
            async with CurlAsyncSession(impersonate="chrome120") as s:
                r = await s.get(url, headers=headers, timeout=20)
                return r.text, r.status_code
        except Exception as e:
            print(f"[debug] fetch error for {url}: {e}")
            return None, 500

    # Fallback to aiohttp if curl_cffi not installed
    import aiohttp
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    return await resp.text(), resp.status
                return None, resp.status
    except Exception as e:
        print(f"[debug] aiohttp error for {url}: {e}")
        return None, 500


async def getChannelData(username):
    """Retrieve channel info and live status from Joystick.tv."""
    channel_urls = [
        f"https://joystick.tv/u/{username}",
        f"https://joystick.tv/{username}"
    ]

    html_text = None
    last_status = 404
    for url in channel_urls:
        html_text, last_status = await fetch_page(url)
        if html_text and last_status == 200:
            break

    if not html_text:
        err_msg = f"HTTP {last_status}"
        if last_status in (403, 503):
            err_msg = "offline / HTTP 403 (Ensure joystick_cookie_str is up-to-date in config.py)"
        return {"success": False, "is_live": False, "error": err_msg}

    # Extract Nuxt 3 data payload
    nuxt_match = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html_text, re.DOTALL)
    if nuxt_match:
        try:
            data = json.loads(nuxt_match.group(1).strip())
            playback_url = None
            avatar_url = None
            stream_title = f"{username} Live Stream"
            is_live = False

            for item in data:
                if isinstance(item, str):
                    if ("live.joystick.tv" in item or "playbackhost" in item) and not playback_url:
                        playback_url = item
                        is_live = True
                    elif "images.joystick.tv" in item and not avatar_url:
                        avatar_url = item

            if is_live and playback_url:
                jwt_token = getattr(config, "joystick_api_key", "").strip().replace("Bearer ", "")
                return {
                    "success": True,
                    "is_live": True,
                    "channel": {
                        "username": username,
                        "id": username,
                        "avatar_url": avatar_url or "https://joystick.tv/favicon.ico",
                    },
                    "stream": {
                        "id": str(int(datetime.now().timestamp())),
                        "title": stream_title,
                        "playback_url": playback_url,
                        "jwt_token": jwt_token,
                    }
                }
        except Exception as e:
            print(f"[debug] Error parsing __NUXT_DATA__: {e}")

    return {
        "success": True,
        "is_live": False,
        "channel": {
            "username": username,
            "id": username,
            "avatar_url": "https://joystick.tv/favicon.ico",
        },
        "stream": None
    }


async def recordLiveStream(filename, data):
    """Download fMP4 segments and pipe directly into FFmpeg."""
    username = data["channel"]["username"]
    directory = os.path.join(BASE_DIR, "captures", username)
    os.makedirs(directory, exist_ok=True)
    mp4_filename = os.path.join(directory, f"{filename}.mp4")

    base_playback = data["stream"]["playback_url"]
    jwt_token = data["stream"].get("jwt_token", "")
    
    # Target the highest resolution track (tracks-v1 or master)
    track_base = f"{base_playback}/tracks-v1/"
    playlist_url = f"{track_base}index.fmp4.m3u8?token={jwt_token}" if jwt_token else f"{track_base}index.fmp4.m3u8"
    init_url = f"{track_base}init.hls.fmp4?token={jwt_token}" if jwt_token else f"{track_base}init.hls.fmp4"

    print(f"[recorder] Capturing live stream to {mp4_filename}")

    # Launch FFmpeg listening on stdin pipe
    cmd = [
        "ffmpeg",
        "-i", "pipe:0",
        "-c", "copy",
        "-movflags", "+faststart",
        "-loglevel", "warning",
        "-y",
        mp4_filename
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    headers = get_request_headers()

    seen_segments = set()
    consecutive_empty = 0
    total_bytes = 0
    segment_count = 0

    if CURL_CFFI_AVAILABLE:
        async with CurlAsyncSession(impersonate="chrome120") as s:
            # 1. Download and pipe init segment
            try:
                init_resp = await s.get(init_url, headers=headers, timeout=15)
                if init_resp.status_code == 200:
                    proc.stdin.write(init_resp.content)
                    proc.stdin.flush()
                    total_bytes += len(init_resp.content)
            except Exception as e:
                print(f"[warning] Failed to fetch init segment: {e}", flush=True)

            # 2. Continuous segment loop
            while True:
                try:
                    p_resp = await s.get(playlist_url, headers=headers, timeout=15)
                    if p_resp.status_code != 200:
                        consecutive_empty += 1
                        if consecutive_empty >= 6:
                            print("[info] Stream ended (playlist offline).", flush=True)
                            break
                        await asyncio.sleep(2.0)
                        continue

                    lines = p_resp.text.splitlines()
                    new_segments_found = False

                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith("#") and line not in seen_segments:
                            seen_segments.add(line)
                            new_segments_found = True
                            seg_url = f"{track_base}{line}"
                            
                            seg_resp = await s.get(seg_url, headers=headers, timeout=15)
                            if seg_resp.status_code == 200:
                                proc.stdin.write(seg_resp.content)
                                proc.stdin.flush()
                                total_bytes += len(seg_resp.content)
                                segment_count += 1
                                mb = total_bytes / (1024 * 1024)
                                print(f"\r[recorder] Segments: {segment_count} | Total: {mb:.1f} MB captured", end="", flush=True)

                    if new_segments_found:
                        consecutive_empty = 0
                    else:
                        consecutive_empty += 1
                        if consecutive_empty >= 15:
                            print("\n[info] Stream ended (no new segments for 30s).", flush=True)
                            break

                except asyncio.CancelledError:
                    print("\n[info] Recording cancelled by user.", flush=True)
                    break
                except KeyboardInterrupt:
                    print("\n[info] Recording stopped by user.", flush=True)
                    break
                except Exception as e:
                    print(f"\n[warning] Segment download error: {e}", flush=True)
                    consecutive_empty += 1
                    if consecutive_empty >= 10:
                        break

                await asyncio.sleep(2.0)

    try:
        proc.stdin.close()
        proc.wait()
    except Exception:
        pass

    final_size_mb = os.path.getsize(mp4_filename) / (1024 * 1024) if os.path.exists(mp4_filename) else 0
    print(f"\n[recorder] Recording complete: {mp4_filename} ({final_size_mb:.1f} MB)", flush=True)
    return mp4_filename


async def generateContactSheet(mp4_filename):
    """Generate thumbnail contact sheet using mt tool."""
    contact_sheet_filename = f"{os.path.splitext(mp4_filename)[0]}.jpg"
    mt_candidates = [
        os.path.join(BASE_DIR, "mt.exe"),
        os.path.join(BASE_DIR, "mt"),
        "mt.exe",
        "mt"
    ]
    mt_exec = next((c for c in mt_candidates if os.path.exists(c)), "mt")

    try:
        command = [
            mt_exec,
            "--columns=4",
            "--numcaps=24",
            "--header-meta",
            "--fast",
            "--comment=Archive - Joystick.tv VODs",
            f"--output={contact_sheet_filename}",
            mp4_filename
        ]
        process = await asyncio.create_subprocess_exec(*command)
        await process.wait()
    except Exception as e:
        print(f"[warning] Contact sheet generator failed: {e}")

    return contact_sheet_filename


async def uploadRecording(mp4_filename, contact_sheet_filename=None):
    """Upload MP4 and optional thumbnail sheet to remote storage via rclone."""
    if not rclone:
        print("[warning] python-rclone module not available, skipping upload.")
        return

    if getattr(config.webhooks, "enabled", False):
        webhook_url = getattr(config.webhooks, "info_webhook", None)
        if webhook_url:
            webhook = DiscordWebhook(url=webhook_url)
            mp4_name = os.path.basename(mp4_filename)
            mention = getattr(config.webhooks, "webhook_mention", "")

            embed = DiscordEmbed(
                title="Joystick.tv Stream Recording Uploaded",
                description=f"Uploaded {mp4_name}",
                color="03b2f8"
            )
            embed.set_timestamp()

            if contact_sheet_filename and os.path.exists(contact_sheet_filename):
                sheet_name = os.path.basename(contact_sheet_filename)
                embed.description += f" with contact sheet {sheet_name}"
                embed.set_image(url=f"attachment://{sheet_name}")
                webhook.add_file(file=open(contact_sheet_filename, "rb"), filename=sheet_name)

            webhook.content = f"{mention} Joystick.tv VOD Uploaded"
            webhook.add_embed(embed)
            try:
                webhook.execute()
                print(f"[info] Sent Discord notification for uploaded {mp4_name}")
            except Exception as e:
                print(f"[warning] Webhook upload notification failed: {e}")

    try:
        if contact_sheet_filename and os.path.exists(contact_sheet_filename) and getattr(config, "mt", False):
            rclone.with_config(rcloneConfig).run_cmd(command="move", extra_args=[contact_sheet_filename, rcloneRemotePath])
        if os.path.exists(mp4_filename):
            rclone.with_config(rcloneConfig).run_cmd(command="move", extra_args=[mp4_filename, rcloneRemotePath])
    except Exception as e:
        print(f"[error] rclone upload error: {e}")


async def sendWebhookLive(data):
    """Send live stream announcement to Discord."""
    webhook_url = getattr(config.webhooks, "live_webhook", None)
    if not webhook_url:
        return

    username = data["channel"]["username"]
    live_url = f"https://joystick.tv/u/{username}"
    mention = getattr(config.webhooks, "webhook_mention", "")
    content = f"{mention} **{username}** is now live on Joystick.tv!"

    embed_live = DiscordEmbed(
        title=data["stream"].get("title", f"{username} is Live!"),
        color="03b2f8",
        url=live_url
    )
    avatar = data["channel"].get("avatar_url", "")
    if avatar:
        embed_live.set_author(name=username, icon_url=avatar)
        embed_live.set_thumbnail(url=avatar)
    embed_live.set_timestamp()

    webhook = DiscordWebhook(url=webhook_url)
    webhook.content = content
    webhook.add_embed(embed_live)

    try:
        response = webhook.execute()
        if response.status_code == 200:
            print(f"[info] Sent Discord live notification for {username}")
    except Exception as e:
        print(f"[warning] Failed to send live webhook: {e}")


async def startRecording(data):
    """Orchestrate recording, conversion, contact sheet, and upload for a live session."""
    username = data["channel"]["username"]
    current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
    stream_id = data["stream"]["id"]
    filename = f"{username}_{current_datetime}_v{stream_id}"

    # 1. Record live stream directly to MP4
    mp4_filename = await recordLiveStream(filename, data)

    # 2. Optional contact sheet
    contact_sheet_filename = None
    if getattr(config, "mt", False) and os.path.exists(mp4_filename):
        contact_sheet_filename = await generateContactSheet(mp4_filename)

    # 3. Optional cloud upload
    if getattr(config, "upload", False) and os.path.exists(mp4_filename):
        await uploadRecording(mp4_filename, contact_sheet_filename)

    print(f"[info] Stream complete. Resuming online check for {username}")
    await asyncio.sleep(checkTimeout)


async def Start():
    """Main monitor loop."""
    if len(sys.argv) < 2:
        print("[Error] Usage: python joystick-recorder.py <username>")
        return

    username = sys.argv[1]
    print(f"[info] Starting Joystick.tv monitor for '{username}'")

    while True:
        try:
            data = await getChannelData(username)

            if data.get("success") and data.get("is_live") and data.get("stream"):
                print(f"[info] {username} is ONLINE! Starting capture...")
                if getattr(config.webhooks, "enabled", False):
                    await sendWebhookLive(data)
                await startRecording(data)
            else:
                status_msg = data.get("error", "offline")
                print(f"[info] {username} is {status_msg}, checking again in {checkTimeout}s")
                await asyncio.sleep(checkTimeout)

        except Exception as e:
            print(f"[error] Unexpected error in monitor loop: {e}")
            await asyncio.sleep(checkTimeout)


if __name__ == "__main__":
    try:
        asyncio.run(Start())
    except KeyboardInterrupt:
        print("\n[info] Exiting monitor.")
