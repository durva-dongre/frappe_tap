"""
shared/submission/object_naming.py

Single source of truth for the tapapp object-key shape, shared by the
attempt-cap check, submission creation, and R2 promotion. Any app writing
submissions into the same bucket layout reuses this unchanged.

Key shape (must match the Worker's own storage/keys.ts byte-for-byte):
    tapapp/{assignment_id}/{student_id}/{submission_id}-{attempt}.{ext}
"""

from __future__ import annotations

import re

from shared.errors import InvalidInput

OBJECT_KEY_RE = re.compile(
    r"^tapapp/(?P<assignment_id>[A-Za-z0-9_-]{1,80})/"
    r"(?P<student_id>[A-Za-z0-9_-]{1,80})/"
    r"(?P<submission_id>[a-z2-7]{6,16})-(?P<attempt>[1-9][0-9]?)\.(?P<ext>[a-z0-9]+)$"
)

EXT_FOR_SUBMISSION_TYPE = {"image": "webp", "video": "mp4"}
CONTENT_TYPE_FOR_SUBMISSION_TYPE = {"image": "image/webp", "video": "video/mp4"}
SUBMISSION_TYPE_FOR_EXT = {v: k for k, v in EXT_FOR_SUBMISSION_TYPE.items()}


def build_object_key(assignment_id: str, student_id: str, submission_id: str, attempt: int, ext: str) -> str:
    return f"tapapp/{assignment_id}/{student_id}/{submission_id}-{attempt}.{ext}"


def parse_object_key(object_key: str) -> dict:
    m = OBJECT_KEY_RE.match(object_key or "")
    if not m:
        raise InvalidInput("object_key does not match the expected shape")
    d = m.groupdict()
    d["attempt"] = int(d["attempt"])
    return d


def submission_type_from_ext(ext: str) -> str | None:
    return SUBMISSION_TYPE_FOR_EXT.get(ext)


def ext_for_submission_type(submission_type: str) -> str | None:
    return EXT_FOR_SUBMISSION_TYPE.get(submission_type)