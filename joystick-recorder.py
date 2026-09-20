import asyncio
from datetime import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

SHUTDOWN_REQUESTED = False

def handle_shutdown_signal(signum, frame):
    global SHUTDOWN_REQUESTED
    print(f"\n[info] Stop signal received ({signum}). Finishing recording and generating MP4 with moov atom...", flush=True)
    SHUTDOWN_REQUESTED = True

try:
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, handle_shutdown_signal)
except Exception:
    pass

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


async def fetch_page(url, use_cookie=True):
    """Fetch URL using curl_cffi or aiohttp."""
    headers = get_request_headers(include_auth=False)
    if not use_cookie and "Cookie" in headers:
        del headers["Cookie"]

    if CURL_CFFI_AVAILABLE:
        try:
            async with CurlAsyncSession(impersonate="firefox") as s:
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
        html_text, last_status = await fetch_page(url, use_cookie=True)
        if html_text and last_status == 200:
            break
        # Fallback without cookie if cookie caused a 403 or 404
        if last_status in (403, 404):
            html_no_cookie, status_no_cookie = await fetch_page(url, use_cookie=False)
            if html_no_cookie and status_no_cookie == 200:
                html_text, last_status = html_no_cookie, status_no_cookie
                break

    if last_status != 200 or not html_text:
        err_msg = f"HTTP {last_status}"
        if last_status in (403, 503):
            err_msg = f"Cloudflare HTTP {last_status}"
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


async def fetch_with_retry(session, url, headers=None, retries=5, timeout=12):
    """Fetch URL with retries and exponential backoff."""
    headers = headers or get_request_headers()
    for i in range(retries):
        try:
            resp = await session.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and len(resp.content) > 0:
                return resp
        except Exception:
            pass
        await asyncio.sleep(0.4 * (i + 1))
    return None


async def recordLiveStream(filename, data):
    """Download video and audio fMP4 segments simultaneously and mux into MP4."""
    username = data["channel"]["username"]
    directory = os.path.join(BASE_DIR, "captures", username)
    os.makedirs(directory, exist_ok=True)
    
    temp_v = os.path.join(directory, f".{filename}_vtmp.mp4")
    temp_a = os.path.join(directory, f".{filename}_atmp.mp4")
    final_mp4 = os.path.join(directory, f"{filename}.mp4")

    base_playback = data["stream"]["playback_url"]
    jwt_token = data["stream"].get("jwt_token", "")
    headers = get_request_headers()

    # Discover audio track folder from master playlist
    audio_folder = "tracks-a2"
    if CURL_CFFI_AVAILABLE:
        try:
            async with CurlAsyncSession(impersonate="firefox") as s:
                m_url = f"{base_playback}/index.m3u8?token={jwt_token}" if jwt_token else f"{base_playback}/index.m3u8"
                m_resp = await fetch_with_retry(s, m_url, headers=headers, retries=3)
                if m_resp:
                    a_match = re.search(r'URI="([^"?]+)', m_resp.text)
                    if a_match:
                        audio_folder = a_match.group(1).split("/")[0]
        except Exception:
            pass

    # Video URLs
    v_base = f"{base_playback}/tracks-v1/"
    v_playlist_url = f"{v_base}index.fmp4.m3u8?token={jwt_token}" if jwt_token else f"{v_base}index.fmp4.m3u8"
    v_init_url = f"{v_base}init.hls.fmp4?token={jwt_token}" if jwt_token else f"{v_base}init.hls.fmp4"

    # Audio URLs
    a_base = f"{base_playback}/{audio_folder}/"
    a_playlist_url = f"{a_base}index.fmp4.m3u8?token={jwt_token}" if jwt_token else f"{a_base}index.fmp4.m3u8"
    a_init_url = f"{a_base}init.hls.fmp4?token={jwt_token}" if jwt_token else f"{a_base}init.hls.fmp4"

    print(f"[recorder] Capturing Video (1080p) + Audio ({audio_folder}) to {final_mp4}", flush=True)

    seen_video = set()
    seen_audio = set()
    consecutive_empty = 0
    total_v_bytes = 0
    total_a_bytes = 0

    if CURL_CFFI_AVAILABLE:
        async with CurlAsyncSession(impersonate="firefox") as s:
            # 1. Fetch init headers before launching FFmpeg
            v_init = await fetch_with_retry(s, v_init_url, headers=headers, retries=5)
            a_init = await fetch_with_retry(s, a_init_url, headers=headers, retries=5)

            if not v_init:
                print(f"[warning] Could not fetch video initialization segment. Aborting stream.")
                return None

            # Launch separate FFmpeg pipes for Video and Audio with fragmented MP4
            # (frag_keyframe+empty_moov writes initial moov header and self-contained fragments so streams are never corrupted if stopped abruptly)
            ffmpeg_v_cmd = [
                "ffmpeg",
                "-i", "pipe:0",
                "-c", "copy",
                "-movflags", "frag_keyframe+empty_moov+default_base_moof",
                "-loglevel", "warning",
                "-y",
                temp_v
            ]
            ffmpeg_a_cmd = [
                "ffmpeg",
                "-i", "pipe:0",
                "-c", "copy",
                "-movflags", "frag_keyframe+empty_moov+default_base_moof",
                "-loglevel", "warning",
                "-y",
                temp_a
            ]

            proc_v = subprocess.Popen(ffmpeg_v_cmd, stdin=subprocess.PIPE)
            proc_a = subprocess.Popen(ffmpeg_a_cmd, stdin=subprocess.PIPE) if a_init else None

            # Write init headers
            proc_v.stdin.write(v_init.content)
            proc_v.stdin.flush()
            total_v_bytes += len(v_init.content)

            if proc_a and a_init:
                proc_a.stdin.write(a_init.content)
                proc_a.stdin.flush()
                total_a_bytes += len(a_init.content)

            # 2. Continuous parallel segment download loop
            while True:
                if SHUTDOWN_REQUESTED:
                    print("\n[info] Stop requested by user. Finishing capture and finalizing MP4...", flush=True)
                    break

                try:
                    new_segments_found = False

                    # Fetch video segments
                    vp_resp = await fetch_with_retry(s, v_playlist_url, headers=headers, retries=2)
                    if vp_resp:
                        for line in vp_resp.text.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#") and line not in seen_video:
                                seen_video.add(line)
                                new_segments_found = True
                                v_seg = await fetch_with_retry(s, f"{v_base}{line}", headers=headers, retries=3)
                                if v_seg:
                                    proc_v.stdin.write(v_seg.content)
                                    proc_v.stdin.flush()
                                    total_v_bytes += len(v_seg.content)

                    # Fetch audio segments
                    if proc_a:
                        ap_resp = await fetch_with_retry(s, a_playlist_url, headers=headers, retries=2)
                        if ap_resp:
                            for line in ap_resp.text.splitlines():
                                line = line.strip()
                                if line and not line.startswith("#") and line not in seen_audio:
                                    seen_audio.add(line)
                                    a_seg = await fetch_with_retry(s, f"{a_base}{line}", headers=headers, retries=3)
                                    if a_seg:
                                        proc_a.stdin.write(a_seg.content)
                                        proc_a.stdin.flush()
                                        total_a_bytes += len(a_seg.content)

                    if new_segments_found:
                        consecutive_empty = 0
                        mb_total = (total_v_bytes + total_a_bytes) / (1024 * 1024)
                        print(f"\r[recorder] Segments: {len(seen_video)} video, {len(seen_audio)} audio | Total: {mb_total:.1f} MB captured", end="", flush=True)
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

            # Finalize and flush both FFmpeg streams
            print("\n[recorder] Flushing FFmpeg streams...", flush=True)
            try:
                if proc_v and proc_v.stdin:
                    proc_v.stdin.close()
                    proc_v.wait(timeout=15)
            except Exception as e:
                print(f"[warning] Video FFmpeg close error: {e}", flush=True)
                try:
                    proc_v.terminate()
                except Exception:
                    pass

            if proc_a:
                try:
                    if proc_a.stdin:
                        proc_a.stdin.close()
                        proc_a.wait(timeout=15)
                except Exception as e:
                    print(f"[warning] Audio FFmpeg close error: {e}", flush=True)
                    try:
                        proc_a.terminate()
                    except Exception:
                        pass

    # Merge Video + Audio into final MP4 with moov atom at beginning (+faststart)
    if os.path.exists(temp_v) and os.path.exists(temp_a) and os.path.getsize(temp_a) > 0 and os.path.getsize(temp_v) > 0:
        print(f"\n[recorder] Finalizing: Muxing video and audio into {final_mp4} with moov atom (+faststart)...", flush=True)
        mux_cmd = [
            "ffmpeg",
            "-i", temp_v,
            "-i", temp_a,
            "-c:v", "copy",
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-loglevel", "warning",
            "-y",
            final_mp4
        ]
        try:
            subprocess.run(mux_cmd, check=True)
            if os.path.exists(final_mp4) and os.path.getsize(final_mp4) > 0:
                print(f"[recorder] Final MP4 generated successfully: {final_mp4}", flush=True)
                try:
                    os.remove(temp_v)
                    os.remove(temp_a)
                except OSError:
                    pass
        except Exception as e:
            print(f"[warning] FFmpeg mux error: {e}. Raw fragmented MP4 tracks preserved: {temp_v}, {temp_a}", flush=True)
    elif os.path.exists(temp_v) and os.path.getsize(temp_v) > 0:
        print(f"\n[recorder] Finalizing: Remuxing video into {final_mp4} with moov atom (+faststart)...", flush=True)
        remux_cmd = [
            "ffmpeg",
            "-i", temp_v,
            "-c", "copy",
            "-movflags", "+faststart",
            "-loglevel", "warning",
            "-y",
            final_mp4
        ]
        try:
            subprocess.run(remux_cmd, check=True)
            if os.path.exists(final_mp4) and os.path.getsize(final_mp4) > 0:
                print(f"[recorder] Final MP4 generated successfully: {final_mp4}", flush=True)
                try:
                    os.remove(temp_v)
                except OSError:
                    pass
        except Exception as e:
            print(f"[warning] FFmpeg remux error: {e}. Preserving {temp_v}", flush=True)
            if not os.path.exists(final_mp4):
                try:
                    os.rename(temp_v, final_mp4)
                except Exception:
                    pass

    final_size_mb = os.path.getsize(final_mp4) / (1024 * 1024) if os.path.exists(final_mp4) else 0
    print(f"[recorder] Recording complete: {final_mp4} ({final_size_mb:.1f} MB)", flush=True)
    return final_mp4


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
    if not mp4_filename or not os.path.exists(mp4_filename):
        print(f"[info] No recording file generated for {username}")
        await asyncio.sleep(checkTimeout)
        return

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
        if SHUTDOWN_REQUESTED:
            print(f"[info] Stopping monitor loop for '{username}'.")
            break

        try:
            data = await getChannelData(username)

            if data.get("success") and data.get("is_live") and data.get("stream"):
                print(f"[info] {username} is ONLINE! Starting capture...")
                if getattr(config.webhooks, "enabled", False):
                    await sendWebhookLive(data)
                await startRecording(data)
                if SHUTDOWN_REQUESTED:
                    print(f"[info] Stop requested during recording. Exiting monitor for '{username}'.")
                    break
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
    except (KeyboardInterrupt, SystemExit):
        print("\n[info] Exiting monitor cleanly.")
