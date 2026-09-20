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
from urllib.parse import unquote

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
        return {"status": "missing", "message": "FANSLY_TOKEN no está configurado en .env"}

    headers = dict(getattr(config, "headers", {}))
    headers["Authorization"] = token

    try:
        r = curl_requests.get("https://apiv3.fansly.com/api/v1/account/me", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("success") and data.get("response"):
                account = data["response"].get("account", {})
                username = account.get("username", "Desconocido")
                user_id = account.get("id", "")
                return {"status": "valid", "message": f"Válido (Conectado como @{username}, ID: {user_id})"}
        if r.status_code == 401:
            return {"status": "expired", "message": "VENCIDO (HTTP 401 Unauthorized - Sesión expirada)"}
        return {"status": "error", "message": f"HTTP {r.status_code}: {r.text[:100]}"}
    except Exception as e:
        return {"status": "error", "message": f"Error de conexión: {e}"}


def check_joystick_cookie():
    """Check Joystick cookie string and Cloudflare clearance."""
    cookie_str = getattr(config, "joystick_cookie_str", "").strip()
    if not cookie_str:
        return {"status": "missing", "message": "JOYSTICK_COOKIE_STR no está configurada en .env"}

    headers = {"Cookie": cookie_str}
    try:
        if CURL_AVAILABLE:
            r = curl_requests.get("https://joystick.tv/", headers=headers, impersonate="firefox", timeout=12)
        else:
            r = curl_requests.get("https://joystick.tv/", headers=headers, timeout=12)

        if r.status_code == 200:
            if "Just a moment..." in r.text or "challenge-running" in r.text:
                return {"status": "expired", "message": "VENCIDA (Cloudflare challenge detectado - cf_clearance caducado)"}
            if "__NUXT" in r.text or "Joystick" in r.text:
                return {"status": "valid", "message": "Válida (HTTP 200 - Autorización de Cloudflare y sitio activa)"}
            return {"status": "valid", "message": "Válida (HTTP 200)"}

        if r.status_code in (403, 503):
            return {"status": "expired", "message": f"VENCIDA o BLOQUEADA (HTTP {r.status_code} - Requiere renovar cf_clearance)"}
        return {"status": "error", "message": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "error", "message": f"Error de conexión: {e}"}


def check_joystick_api_key():
    """Check Joystick streaming API key / token."""
    api_key = getattr(config, "joystick_api_key", "").strip()
    if not api_key:
        return {"status": "missing", "message": "JOYSTICK_API_KEY no está configurada en .env"}

    jwt_payload = parse_jwt(api_key)
    user_desc = ""
    if jwt_payload:
        user_name = jwt_payload.get("name", "")
        user_id = jwt_payload.get("user_id", "")
        user_desc = f" (Usuario: {user_name}, ID: {user_id})"

    # Test edge server authorization with current token
    clean_token = api_key.replace("Bearer ", "").strip()
    try:
        # Test against edge server with MizugiBuns (currently live) or sample endpoint
        test_url = f"https://e5.use1.live.joystick.tv/live/mizugibuns/index.m3u8?token={clean_token}"
        if CURL_AVAILABLE:
            r = curl_requests.get(test_url, impersonate="firefox", timeout=10)
        else:
            r = curl_requests.get(test_url, timeout=10)

        if r.status_code == 200:
            return {"status": "valid", "message": f"Válido{user_desc} (Autorizado para streaming)"}
        elif r.status_code == 403:
            return {"status": "expired", "message": f"VENCIDO{user_desc} (HTTP 403 - Servidor de video rechazó el token)"}
        elif r.status_code == 404:
            # Streamer might be offline, token structure is still intact
            return {"status": "valid", "message": f"Token JWT estructuralmente válido{user_desc}"}
        return {"status": "unknown", "message": f"HTTP {r.status_code}"}
    except Exception as e:
        if jwt_payload:
            return {"status": "valid", "message": f"Token JWT válido localmente{user_desc} (Error de red en test: {e})"}
        return {"status": "error", "message": f"Error: {e}"}


def update_env_variable(key, value):
    """Safely update a variable in the .env file."""
    if not dotenv:
        print("[error] python-dotenv no está instalado.")
        return False

    value = value.strip()
    # Strip accidental enclosing quotes if user pasted them
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]

    try:
        dotenv.set_key(ENV_FILE, key, value)
        print(f"[✓] {key} actualizado exitosamente en {ENV_FILE}")
        return True
    except Exception as e:
        print(f"[error] No se pudo escribir en {ENV_FILE}: {e}")
        return False


def run_diagnostics():
    """Run diagnostics on all configured credentials and print a formatted summary."""
    print("\n" + "=" * 65)
    print("       DIAGNÓSTICO DE CREDENCIALES (INDEPENDIENTE DE NAVEGADOR)")
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

    print("Selecciona qué credencial deseas renovar:")
    print("  1) Joystick Cookie (JOYSTICK_COOKIE_STR)")
    print("  2) Joystick Streaming Key (JOYSTICK_API_KEY)")
    print("  3) Fansly Token (FANSLY_TOKEN)")
    print("  4) Salir")

    try:
        choice = input("\nOpción [1-4]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        return

    mapping = {
        "1": "JOYSTICK_COOKIE_STR",
        "2": "JOYSTICK_API_KEY",
        "3": "FANSLY_TOKEN",
    }

    if choice in mapping:
        key = mapping[choice]
        try:
            new_val = input(f"\nPega el nuevo valor para {key}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelado.")
            return

        if not new_val:
            print("[warning] Valor vacío. No se realizó ningún cambio.")
            return

        if update_env_variable(key, new_val):
            # Reload and recheck
            os.environ[key] = new_val
            import importlib
            importlib.reload(config)
            print("\n[info] Verificando nueva credencial...")
            run_diagnostics()
    elif choice == "4":
        print("Saliendo.")
    else:
        print("[error] Opción no válida.")


def main():
    parser = argparse.ArgumentParser(description="Verificador y renovador de tokens/cookies de stream-recorder")
    parser.add_argument("--renew", action="store_true", help="Abrir menú interactivo para renovar credenciales en .env")
    parser.add_argument("--set-fansly", type=str, help="Actualizar FANSLY_TOKEN directamente")
    parser.add_argument("--set-joystick-cookie", type=str, help="Actualizar JOYSTICK_COOKIE_STR directamente")
    parser.add_argument("--set-joystick-key", type=str, help="Actualizar JOYSTICK_API_KEY directamente")

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
