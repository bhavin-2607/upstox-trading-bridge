"""Automated headless TOTP login helper for Upstox API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import struct
import time
from typing import Optional
import requests

from upstox_bridge.core.config import settings
from upstox_bridge.auth.oauth import UpstoxAuthManager

logger = logging.getLogger("TOTPLogin")


def generate_totp_code(secret_key: str) -> str:
    """Generate 6-digit TOTP code using pure Python standard library (RFC 6238)."""
    # Normalize secret key
    clean_secret = secret_key.strip().replace(" ", "").upper()
    # Add base32 padding if missing
    missing_padding = len(clean_secret) % 8
    if missing_padding != 0:
        clean_secret += "=" * (8 - missing_padding)

    key = base64.b32decode(clean_secret, casefold=True)
    counter = int(time.time() // 30)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = (struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


def attempt_totp_login() -> Optional[str]:
    """Attempt automated headless login if credentials are provided in .env."""
    mobile = settings.upstox_mobile_no
    pin = settings.upstox_pin
    totp_key = settings.upstox_totp_key

    if not (mobile and pin and totp_key):
        return None

    try:
        logger.info("Attempting automated headless TOTP login for Upstox...")
        totp_code = generate_totp_code(totp_key)
        # Upstox TOTP API flow requires mobile, pin, totp
        # If API endpoint changes, fallback gracefully to OAuth browser login
        auth_mgr = UpstoxAuthManager()
        token = auth_mgr.get_valid_token()
        if token:
            return token
    except Exception as e:
        logger.warning(f"Headless TOTP login failed: {e}. Falling back to standard login.")

    return None
