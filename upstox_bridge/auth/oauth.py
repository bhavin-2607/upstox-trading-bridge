"""Upstox OAuth 2.0 flow and token caching."""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Optional
import requests

from upstox_bridge.core.config import settings

logger = logging.getLogger("UpstoxAuth")

UPSTOX_AUTH_DIALOG_URL = "https://api.upstox.com/v2/login/authorization/dialog"
UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


class UpstoxAuthManager:
    """Manages token retrieval, caching, and OAuth interactive authorization."""

    def __init__(self):
        self.api_key = settings.upstox_api_key
        self.api_secret = settings.upstox_api_secret
        self.redirect_uri = settings.upstox_redirect_uri
        self.cache_file = settings.token_cache_path

    def get_valid_token(self) -> Optional[str]:
        """
        Return a valid access token.
        Priority:
        1. UPSTOX_ACCESS_TOKEN from .env (direct manual token provided by user)
        2. Cached token in .token_cache.json (if still valid today)
        """
        # Always prioritize explicit environment token if provided
        env_token = settings.upstox_access_token
        if env_token and len(env_token) > 20:
            return env_token

        # Check local cache
        cached = self._read_cache()
        if cached:
            token = cached.get("access_token")
            expires_at = cached.get("expires_at", 0)
            if token and time.time() < (expires_at - 300):  # 5 min safety buffer
                return token

        return None

    def _read_cache(self) -> Optional[dict]:
        if not self.cache_file.exists():
            return None
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_cache(self, token_data: dict) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2)
            logger.info("Saved fresh Upstox access token to .token_cache.json")
        except Exception as e:
            logger.warning(f"Could not save token cache: {e}")

    def get_login_url(self) -> str:
        """Construct the OAuth login dialog URL."""
        params = {
            "response_type": "code",
            "client_id": self.api_key,
            "redirect_uri": self.redirect_uri,
        }
        return f"{UPSTOX_AUTH_DIALOG_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, auth_code: str) -> dict:
        """Exchange auth code for access token via Upstox API."""
        headers = {
            "accept": "application/json",
            "Api-Version": "2.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        payload = {
            "code": auth_code.strip(),
            "client_id": self.api_key,
            "client_secret": self.api_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }
        resp = requests.post(UPSTOX_TOKEN_URL, data=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        access_token = data.get("access_token")
        if not access_token:
            raise RuntimeError(f"No access_token found in response: {data}")

        # Upstox tokens expire daily around 03:30 AM IST of the following day
        # Calculate expiry timestamp: end of current day + 3 hours
        now = datetime.now()
        tomorrow_3am = (now + timedelta(days=1)).replace(hour=3, minute=30, second=0, microsecond=0)
        expires_at = tomorrow_3am.timestamp()

        cache_payload = {
            "access_token": access_token,
            "user_id": data.get("user_id", ""),
            "user_name": data.get("user_name", ""),
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at,
        }
        self._save_cache(cache_payload)
        return cache_payload

    def interactive_login(self) -> str:
        """
        Interactive login flow:
        Opens browser to Upstox login, captures redirect code automatically or via user input.
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("UPSTOX_API_KEY and UPSTOX_API_SECRET must be set in .env")

        # Parse redirect port if localhost
        parsed_url = urllib.parse.urlparse(self.redirect_uri)
        port = parsed_url.port or 5000
        is_localhost = parsed_url.hostname in ("127.0.0.1", "localhost")

        captured_code: list[str] = []

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                code = params.get("code", [None])[0]
                if code:
                    captured_code.append(code)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    html = (
                        "<html><body style='font-family:sans-serif;text-align:center;padding:50px;'>"
                        "<h2 style='color:#16a34a;'>Authentication Successful!</h2>"
                        "<p>You can close this tab and return to your terminal.</p>"
                        "</body></html>"
                    )
                    self.wfile.write(html.encode("utf-8"))
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"No code received.")

            def log_message(self, format, *args):
                pass  # Suppress HTTP server noise

        server = None
        if is_localhost:
            try:
                server = HTTPServer(("127.0.0.1", port), CallbackHandler)
                server_thread = Thread(target=server.handle_request, daemon=True)
                server_thread.start()
            except Exception as e:
                logger.info(f"Could not bind callback listener on port {port}: {e}")

        login_url = self.get_login_url()
        print("\n" + "=" * 60)
        print("UPSTOX AUTHENTICATION REQUIRED")
        print("=" * 60)
        print("Opening your browser to log in to Upstox...")
        print(f"\nIf the browser does not open automatically, visit this URL:\n{login_url}\n")
        try:
            webbrowser.open(login_url)
        except Exception:
            pass

        if server and is_localhost:
            print(f"Waiting for redirect on {self.redirect_uri} ...")
            # Wait up to 90 seconds for callback
            start_wait = time.time()
            while not captured_code and (time.time() - start_wait) < 90:
                time.sleep(0.5)

        if captured_code:
            code = captured_code[0]
            print("Authorization code received successfully!")
        else:
            print("Automatic redirect capture timed out or unavailable.")
            code = input("Please paste the 'code' parameter from the redirected URL: ").strip()

        if not code:
            raise RuntimeError("Authentication aborted: No auth code provided.")

        result = self.exchange_code_for_token(code)
        print(f"Successfully authenticated as: {result.get('user_name', 'Upstox User')}")
        return result["access_token"]
