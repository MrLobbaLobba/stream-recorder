import aiohttp
import asyncio
from datetime import datetime
import os
import signal
import subprocess
import sys
import time

from os.path import expanduser

from discord_webhook import DiscordWebhook, DiscordEmbed
import config

try:
    import rclone
except ImportError:
    rclone = None

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

rcloneConfig = getattr(config, "rcloneConfig", """
[remote]
type = REPLACE
scope = ALL
token = THIS
""")
rcloneRemotePath = getattr(config, "rcloneRemotePath", "remote:FanslyVODS/")
checkTimeout = getattr(config, "fansly_check_timeout", (2 * 65))

_ALERT_COOLDOWNS = {}

def trigger_alert(alert_key, title, message, level="warning", cooldown_seconds=3600):
    """Notify the user via Console banner, Desktop (notify-send), and Discord Webhook with debounce."""
    now = time.time()
    if alert_key in _ALERT_COOLDOWNS and (now - _ALERT_COOLDOWNS[alert_key]) < cooldown_seconds:
        return
    _ALERT_COOLDOWNS[alert_key] = now

    # 1. Console banner
    print(f"\n{'=' * 65}", flush=True)
    print(f"[ALERTA] {title.upper()}", flush=True)
    print(f"{message}", flush=True)
    print(f"{'=' * 65}\n", flush=True)

    # 2. Desktop notification via Linux notify-send
    try:
        urgency = "critical" if level == "critical" else "normal"
        subprocess.run(
            ["notify-send", "-u", urgency, title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except Exception:
        pass

    # 3. Discord Webhook notification
    if getattr(config.webhooks, "enabled", False):
        webhook_url = getattr(config.webhooks, "info_webhook", None) or getattr(config.webhooks, "live_webhook", None)
        if webhook_url:
            try:
                mention = getattr(config.webhooks, "webhook_mention", "")
                embed = DiscordEmbed(
                    title=f"⚠️ {title}",
                    description=message,
                    color="ff4444" if level == "critical" else "ffaa00"
                )
                embed.set_timestamp()
                webhook = DiscordWebhook(url=webhook_url)
                if mention:
                    webhook.content = f"{mention} Stream Recorder Alert"
                webhook.add_embed(embed)
                webhook.execute()
            except Exception as e:
                print(f"[debug] Failed to send Discord alert: {e}")

async def getAccountData(account_url):
    resolver = aiohttp.resolver.AsyncResolver(
            nameservers=["8.8.8.8", "8.8.8.4", "1.1.1.1", "1.0.0.2"]
    )
    connector = aiohttp.TCPConnector(resolver=resolver)
    try:
        async with aiohttp.ClientSession(connector=connector, headers=config.headers) as session:
            async with session.get(account_url, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status == 401:
                    trigger_alert(
                        "fansly_token_expired",
                        "Fansly: Token de sesión vencido",
                        "La API de Fansly devolvió HTTP 401 Unauthorized. Es necesario renovar FANSLY_TOKEN en tu archivo .env.",
                        level="critical"
                    )
                    return None
                json_data = await response.json()
                if not json_data.get("success") or len(json_data.get("response", [])) == 0:
                    print(f"[warning] Could not retrieve account data: {json_data}")
                    return None

                avatar_obj = json_data["response"][0].get("avatar") or {}
                variants = avatar_obj.get("variants", [])
                locations = variants[0].get("locations", [{}]) if variants else [{}]
                metadata = {
                    "success": json_data["success"],
                    "response": [
                        {
                            "id": json_data["response"][0]["id"],
                            "username": json_data["response"][0]["username"],
                            "avatar": {
                                "id": avatar_obj.get("id"),
                                "mimetype": avatar_obj.get("mimetype"),
                                "location": avatar_obj.get("location"),
                                "variants": [
                                    {
                                        "id": variants[0].get("id") if variants else None,
                                        "mimetype": variants[0].get("mimetype") if variants else None,
                                        "location": variants[0].get("location") if variants else None,
                                        "locations": [
                                            {
                                                "locationId": locations[0].get("locationId"),
                                                "location": locations[0].get("location"),
                                            }
                                        ],
                                    },
                                ],
                            },
                        }
                    ],
                }
                return metadata
    except Exception as e:
        print(f"[warning] Network/DNS error retrieving account data: {e}")
        return None

async def getStreamData(stream_url):
    resolver = aiohttp.resolver.AsyncResolver(
            nameservers=["8.8.8.8", "8.8.8.4", "1.1.1.1", "1.0.0.2"]
    )
    connector = aiohttp.TCPConnector(resolver=resolver)
    try:
        async with aiohttp.ClientSession(connector=connector, headers=config.headers) as session:
            async with session.get(stream_url, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status == 401:
                    trigger_alert(
                        "fansly_token_expired",
                        "Fansly: Token de sesión vencido",
                        "La API de Fansly devolvió HTTP 401 Unauthorized al consultar el stream. Es necesario renovar FANSLY_TOKEN en tu archivo .env.",
                        level="critical"
                    )
                    return {"success": False, "response": None}
                data = await response.json()

        if not data or not data.get("success") or not data.get("response"):
            return {"success": False, "response": None}

        stream_info = data["response"].get("stream")
        if not stream_info:
            return {"success": False, "response": None}

        last_fetched = stream_info.get("lastFetchedAt", 0)
        current_time = int(datetime.now().timestamp() * 1000)
        access = stream_info.get("access")

        if current_time - last_fetched > 2 * 60 * 1000 or not access:
            return {"success": False, "response": None}
        else:
            return {
                "success": True,
                "response": {
                    "id": data["response"]["id"],
                    "accountId": data["response"]["accountId"],
                    "playbackUrl": data["response"]["playbackUrl"],
                    "createdAt": data["response"]["createdAt"],
                    "stream": {
                        "id": stream_info.get("id"),
                        "title": stream_info.get("title"),
                        "status": stream_info.get("status"),
                        "viewerCount": stream_info.get("viewerCount"),
                        "version": stream_info.get("version"),
                        "createdAt": stream_info.get("createdAt"),
                        "lastFetchedAt": stream_info.get("lastFetchedAt"),
                        "startedAt": stream_info.get("startedAt"),
                        "access": stream_info.get("access"),
                        "playbackUrl": stream_info.get("playbackUrl"),
                    },
                },
            }
    except Exception as e:
        print(f"[warning] Network/DNS error fetching stream data: {e}")
        return {"success": False, "response": None}

async def ffmpegSync(filename, data, user_Data):
    global SHUTDOWN_REQUESTED
    username = user_Data["response"][0]["username"]
    directory = os.path.join("./captures", username)
    os.makedirs(directory, exist_ok=True)
    ts_filename = os.path.join(directory, f"{filename}.ts")
    print(f"[ffmpeg] Saving livestream to {ts_filename}")

    stream_url = data["response"]["stream"]["playbackUrl"]
    cmd = [
        "ffmpeg",
        "-i", stream_url,
        "-c", "copy",
        "-movflags", "use_metadata_tags",
        "-map_metadata", "0",
        "-timeout", "300",
        "-reconnect", "300",
        "-reconnect_at_eof", "300",
        "-reconnect_streamed", "300",
        "-reconnect_delay_max", "300",
        "-rtmp_live", "live",
        "-y",
        ts_filename
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        while proc.poll() is None:
            if SHUTDOWN_REQUESTED:
                print("\n[ffmpeg] Stop requested by user. Flushing livestream cleanly...", flush=True)
                try:
                    proc.stdin.write(b"q\n")
                    proc.stdin.flush()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                break
            await asyncio.sleep(1.0)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[ffmpeg] Recording interrupted by user. Stopping capture...", flush=True)
        SHUTDOWN_REQUESTED = True
        try:
            proc.stdin.write(b"q\n")
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.terminate()

    print(f"[ffmpeg] Done saving livestream to {filename}.ts")
    return ts_filename

async def convertToMP4(ts_filename):
    mp4_filename = ts_filename.rsplit('.', 1)[0] + '.mp4'

    if not os.path.exists(ts_filename) or os.path.getsize(ts_filename) == 0:
        print(f"[warning] Source TS file {ts_filename} is empty or does not exist.")
        return None

    print(f"[ffmpeg] Finalizing: Converting {ts_filename} to {mp4_filename} with moov atom (+faststart)...", flush=True)
    command = [
        "ffmpeg",
        "-i", ts_filename,
        "-c:v", "copy",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-loglevel", "warning",
        "-y",
        mp4_filename
    ]
    try:
        subprocess.run(command, check=True)
        if os.path.exists(mp4_filename) and os.path.getsize(mp4_filename) > 0:
            print(f"[info] Successfully generated MP4 with moov atom: {mp4_filename}")
            if getattr(config, "ffmpeg_convert", True):
                try:
                    os.remove(ts_filename)
                except OSError:
                    pass
        else:
            return None
    except Exception as e:
        print(f"[error] FFmpeg conversion failed: {e}")
        return None

    if getattr(config.webhooks, "enabled", False):
        webhook_url = getattr(config.webhooks, "info_webhook", None)
        if webhook_url is not None:
            webhook = DiscordWebhook(url=webhook_url)
            mp4_name = os.path.basename(mp4_filename)
            webhook.content = f"Converted {ts_filename} to {mp4_name}"
            try:
                response = webhook.execute()
                if response.status_code == 200:
                    print(f"[info] Sent Discord notification that {ts_filename} was converted to {mp4_name}")
                else:
                    print(f"[warning] Webhook notification failed: {response.status_code}")
            except Exception as e:
                print(f"[warning] Webhook error: {e}")

    return mp4_filename

async def generateContactSheet(mp4_filename):
    contact_sheet_filename = f"{os.path.splitext(mp4_filename)[0]}.jpg"
    try:
        subprocess.run([
            "./mt",
            "--columns=4",
            "--numcaps=24",
            "--header-meta",
            "--fast",
            "--comment=Archive - Fansly VODs",
            f"--output={contact_sheet_filename}",
            mp4_filename
        ])
    except Exception as e:
        print(f"[warning] Contact sheet generation error: {e}")
    return contact_sheet_filename

async def uploadRecording(mp4_filename, contact_sheet_filename=None):
    if not rclone:
        print("[warning] python-rclone module not available, skipping upload.")
        return

    if getattr(config.webhooks, "enabled", False):
        webhook_url = getattr(config.webhooks, "info_webhook", None)
        if webhook_url is not None:
            webhook = DiscordWebhook(url=webhook_url)
            mp4_name = os.path.basename(mp4_filename)
            sheet_name = os.path.basename(contact_sheet_filename) if contact_sheet_filename else ""
            mention = getattr(config.webhooks, "webhook_mention", "")

            embed = DiscordEmbed(title="Stream Recording Uploaded", description=f'Uploaded {mp4_name}', color="03b2f8")
            if contact_sheet_filename and os.path.exists(contact_sheet_filename):
                embed.description += f" with contact sheet {sheet_name}"
                embed.set_image(url=f"attachment://{sheet_name}")
                webhook.add_file(file=open(contact_sheet_filename, "rb"), filename=sheet_name)
            embed.set_timestamp()

            webhook.content = f"{mention} Vod Uploaded"
            webhook.add_embed(embed)
            try:
                response = webhook.execute()
                if response.status_code == 200:
                    print(f"[info] Sent Discord notification that {mp4_name} was uploaded")
            except Exception as e:
                print(f"[warning] Webhook upload error: {e}")

    try:
        if getattr(config, "mt", False) and contact_sheet_filename and os.path.exists(contact_sheet_filename):
            rclone.with_config(rcloneConfig).run_cmd(command="move", extra_args=[contact_sheet_filename, rcloneRemotePath])
        if os.path.exists(mp4_filename):
            rclone.with_config(rcloneConfig).run_cmd(command="move", extra_args=[mp4_filename, rcloneRemotePath])
    except Exception as e:
        print(f"[error] rclone upload error: {e}")

async def startRecording(user_Data, data):
    global checkTimeout, SHUTDOWN_REQUESTED
    current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{user_Data['response'][0]['username']}_{current_datetime}_v{data['response']['stream']['id']}"

    ts_filename = None
    mp4_filename = None
    try:
        ts_filename = await ffmpegSync(filename, data, user_Data)
    finally:
        # Guarantee that convertToMP4 is ALWAYS executed so the moov atom is generated even on stop!
        if ts_filename and os.path.exists(ts_filename) and os.path.getsize(ts_filename) > 0:
            mp4_filename = await convertToMP4(ts_filename)

    if not mp4_filename or not os.path.exists(mp4_filename):
        return

    contact_sheet_filename = None
    if getattr(config, "mt", False):
        contact_sheet_filename = await generateContactSheet(mp4_filename)

    if getattr(config, "upload", False) and getattr(config, "mt", False) and contact_sheet_filename:
        await uploadRecording(mp4_filename, contact_sheet_filename)
    elif getattr(config, "upload", False):
        await uploadRecording(mp4_filename, None)

    if SHUTDOWN_REQUESTED:
        print("[info] Stopping recording cycle as requested.")
        return

    print(f"[info] Stream complete. Resuming online check")
    await asyncio.sleep(checkTimeout)

async def sendWebhookLive(user_Data):
    webhook_url_startstream = getattr(config.webhooks, "live_webhook", None)
    if not webhook_url_startstream:
        return
    webhook = DiscordWebhook(url=webhook_url_startstream)

    username = user_Data['response'][0]['username']
    live_url = f"https://fansly.com/live/{username}"
    mention = getattr(config.webhooks, "webhook_mention", "")
    content = f"{mention} {username} is now live on Fansly!"
    embed_live = DiscordEmbed(title='Stream Live!', color='03b2f8', url=live_url)
    
    avatar_url = ""
    try:
        avatar_url = user_Data['response'][0]['avatar']['variants'][0]['locations'][0]['location']
    except Exception:
        pass
    if avatar_url:
        embed_live.set_author(name=username, icon_url=avatar_url)
        embed_live.set_thumbnail(url=avatar_url)
    embed_live.set_timestamp()
    webhook.add_embed(embed_live)
    webhook.content = content

    try:
        response = webhook.execute()
        if response.status_code == 200:
            print(f"[info] {username} Stream is online, starting archiver")
        else:
            print(f"[warning] Failed to send webhook notification: {response.status_code}")
    except Exception as e:
        print(f"[warning] Webhook error: {e}")

async def Start():
    if len(sys.argv) < 2:
        print("[Error] Usage: python fansly-recorder.py <username>")
        return

    username = sys.argv[1]   
    account_url = (
        f"https://apiv3.fansly.com/api/v1/account?usernames={username}&ngsw-bypass=true"
    )

    user_Data = None
    while user_Data is None and not SHUTDOWN_REQUESTED:
        user_Data = await getAccountData(account_url)
        if not user_Data:
            print(f"[warning] Could not retrieve account data for {username}, retrying in {checkTimeout}s...")
            await asyncio.sleep(checkTimeout)

    if not user_Data or SHUTDOWN_REQUESTED:
        return

    account_id = user_Data["response"][0]["id"]
    stream_url = f"https://apiv3.fansly.com/api/v1/streaming/channel/{account_id}?ngsw-bypass=true"
    print(f"[info] Starting online check for {user_Data['response'][0]['username']}")

    while True:
        if SHUTDOWN_REQUESTED:
            print(f"[info] Stopping monitor loop for {username}.")
            break

        data = await getStreamData(stream_url)

        if (
            data is not None 
            and data.get("success") 
            and data.get("response")
            and data["response"].get("stream")
            and data["response"]["stream"].get("access")
        ):
            if getattr(config.webhooks, "enabled", False):
                await sendWebhookLive(user_Data)
            print(
                f"[info] {user_Data['response'][0]['username']} Stream is online, starting archiver"
            )
            await startRecording(user_Data, data)
            if SHUTDOWN_REQUESTED:
                print(f"[info] Stop requested during recording. Exiting monitor for {username}.")
                break
        else:
            print(
                f"[info] {user_Data['response'][0]['username']} is offline, checking again in {checkTimeout}s"
            )
            await asyncio.sleep(checkTimeout)


if __name__ == "__main__":
    try:
        asyncio.run(Start())
    except (KeyboardInterrupt, SystemExit):
        print("\n[info] Exiting Fansly monitor cleanly.")
