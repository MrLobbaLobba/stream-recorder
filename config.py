from collections import namedtuple

mt = True # Allows the generation of a contact sheet of thumbnails of the VOD if set to True
upload = True # Allows the usage of rclone to push the VODs to a remote if set to True
ffmpeg_convert = True # If True, uses ffmpeg to convert. If False, renames the .ts file to .mp4 (quicker). 

# Define a named tuple for Webhooks
Webhooks = namedtuple('Webhooks', ['enabled', 'live_webhook', 'info_webhook', 'webhook_mention'])
webhooks = Webhooks(
  enabled=False,  # Set to False if you don't want to use webhooks to be notified
  live_webhook='https://discord.com/api/webhooks/1234567890/abcde',  # Replace with your actual live webhook URL
  info_webhook='https://discord.com/api/webhooks/1234567890/abcde',  # Replace with your actual info webhook URL
  webhook_mention='<@!123456789>' # Replace with the user or role ID you want to mention (@! for user id,@& for role )
)
headers = {
        'authority': 'apiv3.fansly.com',
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en;q=0.8,en-US;q=0.7',
        'authorization': 'your_auth_token_here',  # Replace with your actual auth token
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
joystick_check_timeout = 120  # Seconds between live status checks
joystick_api_key = "your_joystick_api_key_here"

joystick_headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'accept-language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
    'origin': 'https://joystick.tv',
    'referer': 'https://joystick.tv/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0',
}

# Raw cookie string extracted from browser
joystick_cookie_str = "your_joystick_cookies_here"

joystick_cookies = {}
