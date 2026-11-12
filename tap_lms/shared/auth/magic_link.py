from __future__ import annotations

import hmac
import hashlib
import os
import struct
import time

from shared.errors import InvalidInput

DEST_TYPE_BYTE = {"home": 0, "feedback": 1, "submit": 2, "later": 3, "gallery": 4}
_VALID_DEST_TYPES = frozenset(DEST_TYPE_BYTE.keys())

_B32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def _base32_encode(data: bytes) -> str:
    bits = 0
    value = 0
    out = []
    for byte in data:
        value = (value << 8) | byte
        bits += 8
        while bits >= 5:
            out.append(_B32_ALPHABET[(value >> (bits - 5)) & 31])
            bits -= 5
    if bits > 0:
        out.append(_B32_ALPHABET[(value << (5 - bits)) & 31])
    return "".join(out)


def _dash_group(s: str, n: int = 4) -> str:
    return "-".join(s[i:i + n] for i in range(0, len(s), n))


def _pack_phone(phone_digits: str) -> bytes:
    padded = phone_digits.rjust(12, "0")[-12:]
    out = bytearray(6)
    for i in range(6):
        hi = int(padded[i * 2])
        lo = int(padded[i * 2 + 1])
        out[i] = (hi << 4) | lo
    return bytes(out)


def create_magic_link_v2(
    secret: str,
    phone: str,
    dest_type: str = "home",
    dest_id: str | None = None,
    ttl_seconds: int = 90 * 24 * 3600,
) -> str:
    """Mints a V2 magic link byte-for-byte compatible with the Worker's
    auth/magicLink.ts::verifyMagicLinkV2. Minting only — Frappe never
    verifies a magic link; that is exclusively the Worker's job."""
    if dest_type not in _VALID_DEST_TYPES:
        raise InvalidInput("dest_type must be one of: " + ", ".join(sorted(_VALID_DEST_TYPES)))
    if dest_type in ("feedback", "submit") and not dest_id:
        raise InvalidInput(f"dest_id is required for dest_type={dest_type}")

    digits = "".join(c for c in (phone or "") if c.isdigit())
    if not digits or len(digits) > 12:
        raise InvalidInput("phone must be 1-12 digits")

    id_bytes = (dest_id or "").encode("utf-8")
    if len(id_bytes) > 255:
        raise InvalidInput("dest id too long")

    exp = int(time.time()) + ttl_seconds
    nonce = os.urandom(8)
    phone_bytes = _pack_phone(digits)

    body = bytearray()
    body.append(2)  # VERSION
    body.append(DEST_TYPE_BYTE[dest_type])
    body += struct.pack(">I", exp)
    body += nonce
    body += phone_bytes
    body.append(len(id_bytes))
    body += id_bytes

    tag = hmac.new(secret.encode(), bytes(body), hashlib.sha256).digest()[:12]
    combined = bytes(body) + tag
    return _dash_group(_base32_encode(combined))