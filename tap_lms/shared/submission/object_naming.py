"""
shared/submission/object_naming.py

Single source of truth for the tapapp object-key shape, shared by the
attempt-cap check, submission creation, and R2 promotion. Any app writing
submissions into the same bucket layout reuses this unchanged.

Key shape (must match the Worker's own storage/keys.ts byte-for-byte):
    tapapp/{assignment_id}/{student_id}/{submission_id}-{attempt}.{ext}

WIRE SUBMISSION ID RECOVERY (no schema change)
------------------------------------------------
There is deliberately no `worker_submission_id` column on the Submission
doctype, and none will be added. The Worker-minted id embedded in a
submission's object_key is instead recovered PURELY BY COMPUTATION,
on demand, from whichever of two places already holds the information:

  1. The in-memory `object_key` a request already has in hand (used by
     shared.submission.lifecycle.submit_artwork for its OWN immediate
     response, right after creating the row -- see that module).

  2. The row's own `submission_url` field, once populated. For a
     tapapp-sourced submission, tap_lms.imgana.submission.submit_artwork
     creates the row with submission_url=None (see
     _normalize_submission_payload there), and only
     process_submission_async -- enqueued `enqueue_after_commit=True` --
     fills it in afterwards, with (for source == "tapapp") the exact same
     "https://storage.googleapis.com/{bucket}/{object_key}" URL that
     tap_app/api/submission.py::_build_submission_url_from_object_key
     built from object_key before ever calling into lifecycle.submit_artwork
     or imgana. extract_object_key_from_submission_url is the inverse of
     that same build step, and resolve_wire_submission_id is the one
     function every READ path (sync, list, get, gallery_promotion) should
     call to get a submission's Worker-shaped id.

A submission still `Pending`/early-`Processing` (imgana's async job
hasn't run yet) has submission_url still None, so resolve_wire_submission_id
falls back to the Frappe autoname (`sub.name`) for that window -- this is
expected and not a bug: by the time anything actually reads that id again
(sync, list, get, gallery promotion -- which only ever runs post-grading),
submission_url is populated and the Worker-shaped id resolves correctly.

ANY-BUCKET GCS URL PARSING
----------------------------
submission_url is not guaranteed to live under one single, hardcoded
bucket. A submission's media can legitimately sit under any GCS bucket an
operator has configured GCS uploads to write to (e.g.
"https://storage.googleapis.com/assignment_submission_tap/tapapp/..."),
and this module must never assume a specific bucket name anywhere.

extract_object_key_from_submission_url (existing, unchanged below) already
tolerates any bucket for its one job -- recovering the bare object_key --
because it only ever splits on the first "/" after the fixed
"https://storage.googleapis.com/" host prefix and keeps everything after
that first segment intact, discarding only the bucket name itself.

extract_gcs_bucket_and_key is new and additive: it performs the exact same
generic parse, but returns the bucket name alongside the object_key instead
of discarding it. This is needed by
shared.storage.gallery_r2_promotion.promote_submission_media_to_r2, which
must download the ORIGINAL object from GCS before it can copy it to R2, and
so needs to know which bucket to read from -- something
extract_object_key_from_submission_url alone cannot provide. Both functions
share the same parsing rules and the same "return None, never raise, on
anything that doesn't look like a well-formed GCS object URL" contract, so
behavior is identical between the two except for what they return.
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

# Any extension this codebase has ever minted or accepted for an image/video
# submission -- mirrors worker/src/storage/keys.ts::ACCEPTED_FORMATS_FOR
# exactly, so a bucket-agnostic reader (gallery_r2_promotion.py included)
# recognizes every format the Worker's own request_upload could have signed
# for, not just the single recommended default per type (webp / mp4).
EXT_TO_SUBMISSION_TYPE = {
    "webp": "image",
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
    "heic": "image",
    "mp4": "video",
    "mov": "video",
    "webm": "video",
    "3gp": "video",
}

CONTENT_TYPE_TO_SUBMISSION_TYPE = {
    "image/webp": "image",
    "image/jpeg": "image",
    "image/png": "image",
    "image/heic": "image",
    "video/mp4": "video",
    "video/quicktime": "video",
    "video/webm": "video",
    "video/3gpp": "video",
}

# Must match tap_app/api/submission.py::_build_submission_url_from_object_key's
# own URL construction exactly: f"https://storage.googleapis.com/{bucket}/{object_key}".
# This prefix is the ONLY thing about a submission_url this module assumes --
# never a specific bucket name. Everything after the host is generic.
_GCS_URL_PREFIX = "https://storage.googleapis.com/"


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
    """Looks up the Submission.submission_type ("image"/"video") an
    extension implies, across every format this codebase has ever minted
    or accepted -- not just the single recommended default per type. Use
    this (not the narrower EXT_FOR_SUBMISSION_TYPE/SUBMISSION_TYPE_FOR_EXT
    pair above, which only round-trips the *default* ext per type) whenever
    the extension could be any accepted format, such as when reading back
    an arbitrary, already-uploaded object's real extension."""
    if not ext:
        return None
    return EXT_TO_SUBMISSION_TYPE.get(ext.strip().lower())


def submission_type_from_content_type(content_type: str | None) -> str | None:
    """Looks up the Submission.submission_type ("image"/"video") a GCS
    object's reported Content-Type implies, across every format this
    codebase has ever minted or accepted. Returns None for an unrecognized
    or missing content type -- never guesses."""
    if not content_type:
        return None
    base = content_type.split(";", 1)[0].strip().lower()
    return CONTENT_TYPE_TO_SUBMISSION_TYPE.get(base)


def ext_for_submission_type(submission_type: str) -> str | None:
    return EXT_FOR_SUBMISSION_TYPE.get(submission_type)


def extract_object_key_from_submission_url(submission_url: str | None) -> str | None:
    """Recovers the object_key from a Submission's own stored submission_url,
    the exact inverse of tap_app/api/submission.py::
    _build_submission_url_from_object_key's "object_key -> plain public GCS
    URL" construction. Returns None -- never raises -- for any input that
    isn't a real, well-shaped GCS object URL under that fixed host: a
    missing/blank value (including a row whose async upload job hasn't run
    yet -- see module docstring), a URL from some other host entirely (a
    non-tapapp/legacy/whatsapp-sourced submission may have a submission_url
    from a different pipeline altogether), or a URL with no bucket/key
    segment to split out. This is pure, read-only string parsing of data
    Frappe already persisted; it writes nothing and never touches the
    database itself.

    This works identically no matter which bucket the URL names -- it never
    assumes or hardcodes a specific bucket, only the fixed
    "https://storage.googleapis.com/" host prefix. See
    extract_gcs_bucket_and_key below for the variant that also returns the
    bucket name itself.
    """
    parsed = extract_gcs_bucket_and_key(submission_url)
    return parsed[1] if parsed else None


def extract_gcs_bucket_and_key(gcs_url: str | None) -> tuple[str, str] | None:
    """Generic inverse of "bucket + object_key -> plain public GCS URL",
    for ANY bucket -- never tied to one hardcoded bucket name anywhere in
    this codebase. Mirrors worker/src/storage/resign.ts::parseGcsUrl
    exactly: both parse "https://storage.googleapis.com/{bucket}/{key...}"
    generically and return None for anything that doesn't match that
    shape, rather than raising or assuming a specific bucket.

    Returns None -- never raises -- for: a missing/blank value, a "Null"/
    "None" sentinel (the feedback pipeline's convention for "not set yet"),
    a URL from a different host entirely, or a URL with no bucket/key
    segment to split out. Any real, well-formed
    "https://storage.googleapis.com/{bucket}/{key...}" URL parses
    correctly regardless of which bucket it names -- a submission minted
    under "assignment_submission_tap", "tap-submission", or any other
    bucket an operator has GCS uploads configured to write to all parse
    identically here.

    A trailing query string (a previously-signed URL that was, unusually,
    persisted with its signature still attached) is stripped from the
    object_key, exactly as extract_object_key_from_submission_url already
    does for its own return value.
    """
    if not gcs_url or not isinstance(gcs_url, str):
        return None

    trimmed = gcs_url.strip()
    if not trimmed or trimmed.lower() in ("null", "none"):
        return None

    if not trimmed.startswith(_GCS_URL_PREFIX):
        return None

    rest = trimmed[len(_GCS_URL_PREFIX):]
    # rest is "{bucket}/{object_key...}" -- object_key itself contains slashes
    # (tapapp/{assignment_id}/{student_id}/{file}), so split off only the
    # bucket segment and keep everything after it intact.
    parts = rest.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None

    bucket = parts[0]
    # object_key itself never carries a query string, so strip anything
    # from the first "?" onward.
    object_key = parts[1].split("?", 1)[0]
    if not object_key:
        return None

    return bucket, object_key


def resolve_wire_submission_id(sub) -> str:
    """The one function every READ of an EXISTING submission should call to
    get its Worker-shaped submission_id -- shared.profile.sync,
    tap_app/api/submission.py, and shared.storage.gallery_promotion all call
    this instead of reading `sub.name`/`sub["name"]` directly.

    Accepts either a Frappe Document (attribute access) or a plain dict
    (e.g. a frappe.db.sql(as_dict=True) row) -- both shapes are used across
    the three call sites above, so this function supports both rather than
    forcing every caller to normalize first.

    Tries, in order:
      1. Recovering the Worker-minted id from submission_url via
         extract_object_key_from_submission_url + parse_object_key.
      2. Falling back to the Frappe autoname (sub.name / sub["name"]) --
         correct and expected for a submission whose async upload job
         hasn't populated submission_url yet (Pending/early-Processing), or
         whose submission_url never matches the expected tapapp shape (a
         non-tapapp-sourced row, or a malformed/legacy value). This is not
         an error case; see module docstring.

    Never raises: a submission_url that fails to parse is treated exactly
    like a missing one, falling straight through to the autoname.
    """
    if isinstance(sub, dict):
        submission_url = sub.get("submission_url")
        name = sub.get("name")
    else:
        submission_url = getattr(sub, "submission_url", None)
        name = getattr(sub, "name", None)

    object_key = extract_object_key_from_submission_url(submission_url)
    if object_key:
        try:
            parsed = parse_object_key(object_key)
            return parsed["submission_id"]
        except InvalidInput:
            pass

    return name