from __future__ import annotations

import time

import jwt

from shared.config.secrets_cache import get_jwt_secret, get_jwt_algorithm, get_phone_token_ttl_seconds
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
# CONFIGURATION: every value this module needs (jwt_secret, jwt_algorithm,
# phone_token_ttl_seconds) is a real Shared Settings field, read through
# shared/config/secrets_cache.py's dedicated accessors:
#   - get_jwt_secret()            -> Shared Settings.jwt_secret (Password,
#     required -- raises InvalidInput if unconfigured; no safe default for
#     a signing secret)
#   - get_jwt_algorithm()         -> Shared Settings.jwt_algorithm (Data,
#     default "HS256")
#   - get_phone_token_ttl_seconds() -> Shared Settings.phone_token_ttl_seconds
#     (Int, default 7776000 = 90 days; 0 or negative means "no expiry
#     claim at all" -- a real, supported configuration, not an error)
# All three are rotatable/tunable from the Shared Settings doctype UI with
# no deploy, exactly like every other secret/setting in this codebase.
# jwt_secret is intentionally a SEPARATE secret from
# magic_link_shared_secret (shared/auth/magic_link.py) -- the magic link
# and the phone token are different credential types with different
# lifetimes and different verifiers, so they must never share a secret.


def issue_phone_token(phone: str) -> str:
    algorithm = get_jwt_algorithm()
    ttl = get_phone_token_ttl_seconds()
    now = int(time.time())
    claims = {"typ": "phone", "phone": phone, "iat": now}
    if ttl > 0:
        claims["exp"] = now + ttl
    return jwt.encode(claims, get_jwt_secret(), algorithm=algorithm)


def verify_phone_token(token: str) -> dict:
    algorithm = get_jwt_algorithm()
    try:
        claims = jwt.decode(token, get_jwt_secret(), algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise Unauthorized("token expired", error_code="token_expired")
    except jwt.InvalidTokenError:
        raise Unauthorized("token invalid", error_code="token_invalid")
    if claims.get("typ") != "phone" or not claims.get("phone"):
        raise Unauthorized("token invalid", error_code="token_invalid")
    return claims