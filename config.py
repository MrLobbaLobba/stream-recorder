import os
from collections import namedtuple
from dotenv import load_dotenv

# Load .env file from project root directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

mt = True # Allows the generation of a contact sheet of thumbnails of the VOD if set to True
upload = True # Allows the usage of rclone to push the VODs to a remote if set to True
ffmpeg_convert = True # If True, uses ffmpeg to convert. If False, renames the .ts file to .mp4 (quicker). 

# Define a named tuple for Webhooks
Webhooks = namedtuple('Webhooks', ['enabled', 'live_webhook', 'info_webhook', 'webhook_mention'])
webhooks = Webhooks(
  enabled=os.getenv('DISCORD_WEBHOOKS_ENABLED', 'false').lower() in ('true', '1', 'yes'),
  live_webhook=os.getenv('DISCORD_LIVE_WEBHOOK', 'https://discord.com/api/webhooks/1234567890/abcde'),
  info_webhook=os.getenv('DISCORD_INFO_WEBHOOK', 'https://discord.com/api/webhooks/1234567890/abcde'),
  webhook_mention=os.getenv('DISCORD_WEBHOOK_MENTION', '<@!123456789>')
)

# Fansly configuration
fansly_token = os.getenv('FANSLY_TOKEN', 'your_auth_token_here')

headers = {
        'authority': 'apiv3.fansly.com',
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en;q=0.8,en-US;q=0.7',
        'authorization': fansly_token,
        'origin': 'https://fansly.com',
        'referer': 'https://fansly.com/',
        'sec-ch-ua': '"Not.A/Brand";v="8", "Chromium";v="114", "Google Chrome";v="114"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
}

# --- Joystick.tv Settings ---
joystick_check_timeout = int(os.getenv('JOYSTICK_CHECK_TIMEOUT', '120'))
joystick_api_key = os.getenv('JOYSTICK_API_KEY', '')

joystick_headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'accept-language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
    'origin': 'https://joystick.tv',
    'referer': 'https://joystick.tv/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0',
}

# Raw cookie string extracted from browser
joystick_cookie_str = os.getenv('JOYSTICK_COOKIE_STR', '')

joystick_cookies = {}

