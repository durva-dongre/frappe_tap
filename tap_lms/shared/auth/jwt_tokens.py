from __future__ import annotations

import time

import jwt

from shared.config.secrets_cache import get_jwt_secret
from shared.config.settings_cache import get, get_int
from shared.errors import Unauthorized

# One token type in this module: phone-scoped. No student-scoped token, no
# session layer, no server-side registry -- verification is pure signature+exp
# decode, zero Redis/Postgres involved, so it costs nothing under concurrent load
# and is identical whether redeemed the same second it's issued or a year later.
#
# Any sibling sharing a phone can use the same token for any of their own
# student_ids on this phone -- per-request ownership of a specific student_id is
# enforced separately (roster.student_belongs_to_phone), never baked into claims.
# TTL is long (phone_token_ttl_seconds, default 90 days) since there's no
# session/refresh layer and re-logging in via the magic link should be rare.
#
# DEPENDENCY NOTE: this module references get_jwt_secret (not currently in
# secrets_cache.py), get/get_int (not currently in settings_cache.py), and
# Unauthorized (not currently in errors.py). Resolving those additions is
# outside this module's own scope; callers relying on this file should
# confirm those symbols exist in their target shared/ package before use.


def issue_phone_token(phone: str) -> str:
    algorithm = get("jwt_algorithm", "HS256")
    ttl = get_int("phone_token_ttl_seconds", 7776000)
    now = int(time.time())
    claims = {"typ": "phone", "phone": phone, "iat": now}
    if ttl > 0:
        claims["exp"] = now + ttl
    return jwt.encode(claims, get_jwt_secret(), algorithm=algorithm)


def verify_phone_token(token: str) -> dict:
    algorithm = get("jwt_algorithm", "HS256")
    try:
        claims = jwt.decode(token, get_jwt_secret(), algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("token expired", error_code="token_expired")
    except jwt.InvalidTokenError:
        raise Unauthorized("token invalid", error_code="token_invalid")
    if claims.get("typ") != "phone" or not claims.get("phone"):
        raise Unauthorized("token invalid", error_code="token_invalid")
    return claims