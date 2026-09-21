#!/usr/bin/env python3
"""
Credentials & Token Diagnostic and Renewal Utility
Checks Fansly and Joystick credentials independently of any browser,
and provides easy renewal directly into the .env file.
"""

import argparse
import base64
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

ENV_FILE = os.path.join(BASE_DIR, ".env")

try:
    import dotenv
except ImportError:
    dotenv = None

try:
    from curl_cffi import requests as curl_requests
    CURL_AVAILABLE = True
except ImportError:
    CURL_AVAILABLE = False
    import requests as curl_requests

import config


def parse_jwt(token_str):
    """Safely decode and parse JWT payload without external libraries."""
    token = token_str.replace("Bearer ", "").strip()
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")))
    except Exception:
        return None


def check_fansly():
    """Check Fansly session token."""
    token = getattr(config, "fansly_token", "").strip()
    if not token:
        return {"status": "missing", "message": "FANSLY_TOKEN is not configured in .env"}

    headers = dict(getattr(config, "headers", {}))
    headers["Authorization"] = token

    try:
        r = curl_requests.get("https://apiv3.fansly.com/api/v1/account/me", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("success") and data.get("response"):
                account = data["response"].get("account", {})
                username = account.get("username", "Unknown")
                user_id = account.get("id", "")
                return {"status": "valid", "message": f"Valid (Connected as @{username}, ID: {user_id})"}
        if r.status_code == 401:
            return {"status": "expired", "message": "EXPIRED (HTTP 401 Unauthorized - Session expired)"}
        return {"status": "error", "message": f"HTTP {r.status_code}: {r.text[:100]}"}
    except Exception as e:
        return {"status": "error", "message": f"Connection error: {e}"}


def check_joystick_cookie():
    """Check Joystick cookie string and Cloudflare clearance."""
    cookie_str = getattr(config, "joystick_cookie_str", "").strip()
    if not cookie_str:
        return {"status": "missing", "message": "JOYSTICK_COOKIE_STR is not configured in .env"}

    headers = {"Cookie": cookie_str}
    try:
        if CURL_AVAILABLE:
            r = curl_requests.get("https://joystick.tv/", headers=headers, impersonate="firefox", timeout=12)
        else:
            r = curl_requests.get("https://joystick.tv/", headers=headers, timeout=12)

        if r.status_code == 200:
            if "Just a moment..." in r.text or "challenge-running" in r.text:
                return {"status": "expired", "message": "EXPIRED (Cloudflare challenge detected - cf_clearance expired)"}
            if "__NUXT" in r.text or "Joystick" in r.text:
                return {"status": "valid", "message": "Valid (HTTP 200 - Cloudflare clearance & site active)"}
            return {"status": "valid", "message": "Valid (HTTP 200)"}

        if r.status_code in (403, 503):
            return {"status": "expired", "message": f"EXPIRED or BLOCKED (HTTP {r.status_code} - Requires fresh cf_clearance)"}
        return {"status": "error", "message": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "error", "message": f"Connection error: {e}"}


def check_joystick_api_key():
    """Check Joystick streaming API key / token."""
    api_key = getattr(config, "joystick_api_key", "").strip()
    if not api_key:
        return {"status": "missing", "message": "JOYSTICK_API_KEY is not configured in .env"}

    jwt_payload = parse_jwt(api_key)
    if not jwt_payload:
        return {"status": "invalid", "message": "Invalid JWT format (Check JOYSTICK_API_KEY in .env)"}

    user_name = jwt_payload.get("name", "")
    user_id = jwt_payload.get("user_id", "")
    user_desc = f" (User: {user_name}, ID: {user_id})"

    # Check 'exp' claim if present
    exp = jwt_payload.get("exp")
    if exp:
        now = time.time()
        if now > exp:
            return {"status": "expired", "message": f"EXPIRED{user_desc} (Expired at timestamp {exp})"}
        remaining_hours = (exp - now) / 3600
        return {"status": "valid", "message": f"Valid{user_desc} (Expires in {remaining_hours:.1f} hours)"}

    iat = jwt_payload.get("iat")
    iat_desc = f", Issued: {time.strftime('%Y-%m-%d', time.gmtime(iat))}" if iat else ""
    return {"status": "valid", "message": f"Valid JWT token{user_desc}{iat_desc}"}


def update_env_variable(key, value):
    """Safely update a variable in the .env file."""
    if not dotenv:
        print("[error] python-dotenv is not installed.")
        return False

    value = value.strip()
    # Strip accidental enclosing quotes if user pasted them
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]

    try:
        dotenv.set_key(ENV_FILE, key, value)
        print(f"[✓] {key} successfully updated in {ENV_FILE}")
        return True
    except Exception as e:
        print(f"[error] Could not write to {ENV_FILE}: {e}")
        return False


def run_diagnostics():
    """Run diagnostics on all configured credentials and print a formatted summary."""
    print("\n" + "=" * 65)
    print("       CREDENTIAL DIAGNOSTICS (BROWSER-INDEPENDENT)")
    print("=" * 65)

    # 1. Fansly
    fansly_res = check_fansly()
    icon = "✓" if fansly_res["status"] == "valid" else ("✗" if fansly_res["status"] == "expired" else "!")
    print(f"[{icon}] Fansly Token: {fansly_res['message']}")

    # 2. Joystick Cookie
    joy_cookie_res = check_joystick_cookie()
    icon = "✓" if joy_cookie_res["status"] == "valid" else ("✗" if joy_cookie_res["status"] == "expired" else "!")
    print(f"[{icon}] Joystick Cookie (cf_clearance): {joy_cookie_res['message']}")

    # 3. Joystick Streaming Key
    joy_key_res = check_joystick_api_key()
    icon = "✓" if joy_key_res["status"] == "valid" else ("✗" if joy_key_res["status"] == "expired" else "!")
    print(f"[{icon}] Joystick Streaming Key: {joy_key_res['message']}")

    print("=" * 65 + "\n")
    return {
        "fansly": fansly_res,
        "joystick_cookie": joy_cookie_res,
        "joystick_key": joy_key_res,
    }


def interactive_renewal():
    """Interactive CLI menu to renew credentials."""
    results = run_diagnostics()

    print("Select which credential you want to renew:")
    print("  1) Joystick Cookie (JOYSTICK_COOKIE_STR)")
    print("  2) Joystick Streaming Key (JOYSTICK_API_KEY)")
    print("  3) Fansly Token (FANSLY_TOKEN)")
    print("  4) Exit")

    try:
        choice = input("\nChoice [1-4]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return

    mapping = {
        "1": "JOYSTICK_COOKIE_STR",
        "2": "JOYSTICK_API_KEY",
        "3": "FANSLY_TOKEN",
    }

    if choice in mapping:
        key = mapping[choice]
        try:
            new_val = input(f"\nPaste the new value for {key}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return

        if not new_val:
            print("[warning] Empty value provided. No changes made.")
            return

        if update_env_variable(key, new_val):
            os.environ[key] = new_val
            import importlib
            importlib.reload(config)
            print("\n[info] Verifying updated credential...")
            run_diagnostics()
    elif choice == "4":
        print("Exiting.")
    else:
        print("[error] Invalid option.")


def main():
    parser = argparse.ArgumentParser(description="Stream-recorder token and cookie diagnostic and renewal utility")
    parser.add_argument("--renew", action="store_true", help="Open interactive menu to renew credentials in .env")
    parser.add_argument("--set-fansly", type=str, help="Update FANSLY_TOKEN directly")
    parser.add_argument("--set-joystick-cookie", type=str, help="Update JOYSTICK_COOKIE_STR directly")
    parser.add_argument("--set-joystick-key", type=str, help="Update JOYSTICK_API_KEY directly")

    args = parser.parse_args()

    if args.set_fansly:
        update_env_variable("FANSLY_TOKEN", args.set_fansly)
    elif args.set_joystick_cookie:
        update_env_variable("JOYSTICK_COOKIE_STR", args.set_joystick_cookie)
    elif args.set_joystick_key:
        update_env_variable("JOYSTICK_API_KEY", args.set_joystick_key)
    elif args.renew:
        interactive_renewal()
    else:
        run_diagnostics()


if __name__ == "__main__":
    main()
