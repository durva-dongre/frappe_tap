"""
shared/submission/object_naming.py

Single source of truth for the tapapp object-key shape, shared by the
attempt-cap check, submission creation, and R2 promotion. Any app writing
submissions into the same bucket layout reuses this unchanged.

Key shape (must match the Worker's own storage/keys.ts byte-for-byte, FOR
THE GCS KEY -- the key the Worker mints and the client uploads to):
    tapapp/{assignment_id}/{student_id}/{submission_id}-{attempt}.{ext}

OBJECT_KEY_RE tolerates a space inside assignment_id/student_id, matching the
Worker's own GCS-side shape exactly: the Worker's storage/keys.ts::
FIELD_PATTERNS.assignment_id is /^[A-Za-z0-9_ -]{3,80}$/ -- space-tolerant --
because a legacy/WhatsApp-sourced assignment_id such as "Spaceship
Assignment-62591" is a real, legitimate value. The GCS object key the Worker
mints for that assignment_id contains that literal space verbatim.

build_object_key always produces the SANITIZED (no-space) key shape used for
R2 storage and the gallery's D1 index -- it sanitizes assignment_id and
student_id via sanitize_key_segment before building the key. parse_object_key
must still be able to parse the raw, space-tolerant GCS key shape too, which
is why OBJECT_KEY_RE stays space-tolerant even though build_object_key never
emits a space itself.

ASSIGNMENT_ID SCOPE NORMALIZATION
-----------------------------------
normalize_assignment_id_for_scope() is the one function every caller must use
instead of hand-rolling sanitization, whenever assignment_id is being written
to, or compared against, a D1/gallery scope value. It is a thin, named wrapper
around sanitize_key_segment, kept as a separate function (rather than callers
calling sanitize_key_segment directly) so:
  - every write site (shared/jobs/gallery_promotion_sweep.py) and every read
    site (shared/profile/student.py::get_profile_scope) are provably calling
    the exact same transform, not two independently-maintained copies that
    can quietly drift apart;
  - a future change to the normalization rule only has one call site to
    update, not N.
Without this, a real, exactly-matching assignment_id containing a space could
be written to D1 as one sanitized string by the sweep and read back as a
differently (or not-at-all) sanitized string by profile scope resolution --
silently breaking the gallery's narrowest, most relevant cascade level for
any assignment_id that isn't already punctuation-free.

sanitize_scope_value, separately, sanitizes the gallery's state/district/
school D1 columns against a DIFFERENT, stricter character class (lowercase
[a-z0-9-] only, no underscore) -- that is a distinct field with a distinct
rule, not interchangeable with normalize_assignment_id_for_scope /
sanitize_key_segment.

WIRE SUBMISSION ID RECOVERY (no schema change)
------------------------------------------------
There is deliberately no `worker_submission_id` column on the Submission
doctype, and none will be added. The Worker-minted id embedded in a
submission's object_key is instead recovered PURELY BY COMPUTATION, on
demand, from whichever of two places already holds the information:

  1. The in-memory `object_key` a request already has in hand (used by
     shared.submission.lifecycle.submit_artwork for its OWN immediate
     response, right after creating the row).

  2. The row's own `submission_url` field, once populated. For a
     tapapp-sourced submission, tap_lms.imgana.submission.submit_artwork
     creates the row with submission_url=None, and only
     process_submission_async -- enqueued `enqueue_after_commit=True` --
     fills it in afterwards, with (for source == "tapapp") the exact same
     "https://storage.googleapis.com/{bucket}/{object_key}" URL that
     tap_app/api/submission.py::_build_submission_url_from_object_key built
     from object_key before ever calling into lifecycle.submit_artwork or
     imgana. extract_object_key_from_submission_url is the inverse of that
     same build step, and resolve_wire_submission_id is the one function
     every READ path (sync, list, get, gallery_promotion, the nightly
     gallery_promotion_sweep) should call to get a submission's
     Worker-shaped id.

A submission still Pending/early-Processing (imgana's async job hasn't run
yet) has submission_url still None, so resolve_wire_submission_id falls back
to the Frappe autoname (`sub.name`) for that window -- this is expected and
not a bug: by the time anything actually reads that id again (sync, list,
get, gallery promotion -- which only ever runs post-grading),
submission_url is populated and the Worker-shaped id resolves correctly.

Previously, the nightly gallery sweep's own payload builder wrote
sub["name"] (Frappe's raw document name) directly into D1's
gallery_items.submission_id, instead of calling resolve_wire_submission_id --
a different, inconsistent scheme from every other read path. That mismatch
is fixed at the sweep's own call site (shared/jobs/gallery_promotion_sweep.py),
not in this module; this module's resolve_wire_submission_id was already
correct and is simply the function that call site now actually uses.

ANY-BUCKET GCS URL PARSING
----------------------------
submission_url is not guaranteed to live under one single, hardcoded bucket.
extract_gcs_bucket_and_key and extract_object_key_from_submission_url both
parse "https://storage.googleapis.com/{bucket}/{key...}" generically, for
ANY bucket, mirroring the Worker's own storage/resign.ts::parseGcsUrl.
"""

from __future__ import annotations

import re

from shared.errors import InvalidInput

# Bounds match the Worker's GCS-side shape exactly:
#   - assignment_id / student_id: {3,80}, matching worker/src/storage/keys.ts::
#     FIELD_PATTERNS.assignment_id / FIELD_PATTERNS.student_id -- BOTH of
#     which are SPACE-TOLERANT ([A-Za-z0-9_ -]) on the Worker's own GCS-key
#     side. This is deliberately WIDER than
#     worker/src/handlers/internalHandlers.ts::OBJECT_KEY_PATTERN, which
#     validates the separate, SANITIZED R2 key (no space) -- the two keys
#     are different strings for different purposes, and this regex parses
#     the former, not the latter.
#   - ext: {1,10}, matching worker/src/storage/keys.ts's filename regex
#     ([a-zA-Z0-9]{1,10}) and OBJECT_KEY_PATTERN's own [A-Za-z0-9]{1,10}.
OBJECT_KEY_RE = re.compile(
    r"^tapapp/(?P<assignment_id>[A-Za-z0-9_ -]{3,80})/"
    r"(?P<student_id>[A-Za-z0-9_ -]{3,80})/"
    r"(?P<submission_id>[a-z2-7]{6,16})-(?P<attempt>[1-9][0-9]?)\.(?P<ext>[a-z0-9]{1,10})$"
)

# Matches the Worker's OBJECT_KEY_PATTERN character class for the
# assignment_id/student_id path segments exactly: [A-Za-z0-9_-]. Anything
# outside this set (spaces, punctuation, unicode, etc.) is replaced with a
# single '-' by sanitize_key_segment below, so a raw, unvalidated
# assignment_id/student_id can always be safely interpolated into an R2
# object key. This remains the NARROWER, R2-side rule -- distinct from
# OBJECT_KEY_RE above, which parses the raw, space-tolerant GCS key.
_KEY_SEGMENT_DISALLOWED_CHARS = re.compile(r"[^A-Za-z0-9_-]")

# Matches the Worker's GALLERY_SCOPE_FIELD_PATTERNS character class for
# state/district/school exactly: lowercase [a-z0-9-] ONLY -- no underscore,
# unlike _KEY_SEGMENT_DISALLOWED_CHARS above, which is a different, looser
# rule for a different field (an object-key path segment, not a D1 gallery
# scope column). A RUN of one or more disallowed characters collapses to a
# SINGLE '-' (not one '-' per disallowed character).
_SCOPE_VALUE_DISALLOWED_CHARS = re.compile(r"[^a-z0-9-]+")

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


def sanitize_key_segment(value: str) -> str:
    """Replaces every character not in [A-Za-z0-9_-] with '-', so the result
    is always safe to interpolate into an R2/GCS object key's assignment_id
    or student_id path segment, and always matches the Worker's own
    OBJECT_KEY_PATTERN character class for that segment.

    This exists because callers of build_object_key are not guaranteed to
    have already validated their assignment_id/student_id against the
    Worker's stricter R2-side key-segment shape. FIELD_PATTERNS.assignment_id
    is more permissive -- it allows a literal space -- so a legacy/
    WhatsApp-sourced assignment_id like "Spaceship Assignment-62591" passes
    that check but still contains a character the Worker's
    OBJECT_KEY_PATTERN will reject once it reaches /internal/gallery/index.
    Sanitizing once, here, at key-build time, means every caller of
    build_object_key gets a key that downstream gallery indexing will always
    accept, instead of each caller needing to remember to pre-sanitize its
    own inputs.

    normalize_assignment_id_for_scope() below wraps this exact function for
    the specific case of a D1/gallery SCOPE value (not a key path segment) --
    see that function's own docstring for why it exists as a separate, named
    call.

    Leading/trailing whitespace is stripped first, then every remaining
    disallowed character (including any interior whitespace, punctuation, or
    non-ASCII character) is replaced with a single '-'. An empty or falsy
    input is returned unchanged.

    NOTE: this replaces each individual disallowed character with its own
    '-' (so "A  B" becomes "A--B", not "A-B") -- kept exactly as originally
    shipped, since object-key uniqueness/collision behavior for this
    function is already relied upon elsewhere and should not change here.
    """
    if not value:
        return value
    return _KEY_SEGMENT_DISALLOWED_CHARS.sub("-", value.strip())


def normalize_assignment_id_for_scope(value: str | None) -> str | None:
    """The one normalization assignment_id goes through before being stored
    as a D1/gallery scope value, OR before being used to query one.

    Every caller that writes or compares against a stored assignment_id must
    call this function -- never sanitize_key_segment directly for this
    purpose, and never re-implement the transform inline. This is what keeps
    the write side (shared/jobs/gallery_promotion_sweep.py's nightly D1
    payload builder) and the read side (shared/profile/student.py::
    get_profile_scope, whose result the Worker's gallery query binds
    directly into `WHERE assignment_id = ?1`) provably producing the exact
    same string for the exact same raw input -- including a raw
    assignment_id that contains a space, such as a legacy/WhatsApp-sourced
    "Spaceship Assignment-62591".

    Internally this is exactly sanitize_key_segment (collapses whitespace/
    punctuation to '-', character-by-character). It is named and exported
    separately purely so a reader of either call site immediately sees "this
    is the gallery scope normalization," not "this happens to call the same
    function the object-key builder uses." If the two transforms ever need
    to diverge in the future, this is the one place to change for every
    scope-related caller at once.

    Returns None for an empty/falsy input -- there is nothing to normalize,
    and callers can write `normalize_assignment_id_for_scope(raw)` directly
    without an extra `if raw else None` guard at the call site.
    """
    if not value:
        return None
    return sanitize_key_segment(value)


def sanitize_scope_value(value: str | None) -> str | None:
    """Sanitizes a state/district/school value for the gallery's D1 scope
    columns, so it always matches the Worker's own GALLERY_SCOPE_FIELD_
    PATTERNS exactly -- lowercase, [a-z0-9-]{2,60} only, no underscore.

    This exists because Student.state_id / district_id / school_id are
    Frappe Link doc-names, and nothing guarantees those names are already
    shaped to the Worker's stricter scope-value pattern. School.name in
    particular is autonamed as "format:{name1}-SC{#####}", so it can
    contain a literal space whenever name1 does (e.g.
    "Green Valley School-SC00536"); State.name/District.name happen to BE
    their own display string by autoname convention, but are not guaranteed
    to be free of spaces or other punctuation either.

    Every RUN of one or more disallowed characters (anything other than
    a-z, 0-9, or '-') collapses to a SINGLE '-' (not one '-' per disallowed
    character, unlike sanitize_key_segment above) -- so "mumbai suburban"
    becomes "mumbai-suburban" and "Green Valley School-SC00536" becomes
    "green-valley-school-sc00536", both now valid against
    /^[a-z0-9-]{2,60}$/. Leading/trailing whitespace is stripped first, and
    any leading/trailing '-' left over after collapsing is stripped too, so
    a value that was entirely disallowed characters doesn't produce a bare
    "-" string.

    Returns None for a falsy input, or for a value that becomes empty after
    stripping disallowed characters -- callers do not need a separate
    `or None` at the call site.

    READ-PATH CAVEAT: this only affects the WRITE path into D1. The
    gallery's READ-side scope resolution (worker/src/storage/
    profileScope.ts::normalizeScopeValue) only lowercases and trims -- it
    does NOT collapse punctuation. If a student's live profile scope value
    itself contains a space or other disallowed character, the Worker's own
    read-side normalization will not produce the same string this function
    wrote to D1. Confirming end-to-end scope matching for such values is a
    separate, Worker-side concern.
    """
    if not value:
        return None
    collapsed = _SCOPE_VALUE_DISALLOWED_CHARS.sub("-", value.strip().lower())
    stripped = collapsed.strip("-")
    return stripped or None


def build_object_key(assignment_id: str, student_id: str, submission_id: str, attempt: int, ext: str) -> str:
    """Builds the tapapp object key, sanitizing assignment_id and student_id
    first (see sanitize_key_segment) so the result always matches the
    Worker's own OBJECT_KEY_PATTERN, regardless of whether the caller's raw
    inputs already did. submission_id and ext are not sanitized here --
    submission_id is always Worker-minted ([a-z2-7]{6,16}) and ext is always
    resolved from a fixed, known-safe table, so neither can contain a
    character this function would need to clean up.

    NOTE: this function always produces the SANITIZED (no-space) key shape,
    used for R2 storage and for the gallery's D1 index. The raw GCS key the
    Worker mints for the actual upload does NOT sanitize, and can
    legitimately contain a space in assignment_id/student_id --
    parse_object_key below (backed by OBJECT_KEY_RE) must be able to parse
    THAT raw shape too, which is why OBJECT_KEY_RE is space-tolerant even
    though this function never emits a space itself.
    """
    safe_assignment_id = sanitize_key_segment(assignment_id)
    safe_student_id = sanitize_key_segment(student_id)
    return f"tapapp/{safe_assignment_id}/{safe_student_id}/{submission_id}-{attempt}.{ext}"


def parse_object_key(object_key: str) -> dict:
    """Parses a tapapp object key -- either the raw, space-tolerant shape the
    Worker mints for a GCS upload, or the sanitized, no-space shape
    build_object_key produces for R2/gallery storage. See OBJECT_KEY_RE's own
    comment above for why the pattern tolerates a space: this function must
    successfully parse BOTH shapes, since callers such as
    shared.submission.lifecycle._validate_object_key_attempt receive the
    client-supplied, UNSANITIZED object_key (the one the Worker actually
    minted and the client actually uploaded to), not a sanitized copy."""
    m = OBJECT_KEY_RE.match(object_key or "")
    if not m:
        raise InvalidInput("object_key does not match the expected shape")
    d = m.groupdict()
    d["attempt"] = int(d["attempt"])
    return d


def submission_type_from_ext(ext: str) -> str | None:
    """Looks up the Submission.submission_type ("image"/"video") an
    extension implies, across every format this codebase has ever minted or
    accepted -- not just the single recommended default per type. Use this
    (not the narrower EXT_FOR_SUBMISSION_TYPE/SUBMISSION_TYPE_FOR_EXT pair
    above, which only round-trips the *default* ext per type) whenever the
    extension could be any accepted format, such as when reading back an
    arbitrary, already-uploaded object's real extension."""
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
    yet), a URL from some other host entirely, or a URL with no bucket/key
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
    """Generic inverse of "bucket + object_key -> plain public GCS URL", for
    ANY bucket -- never tied to one hardcoded bucket name anywhere in this
    codebase. Mirrors worker/src/storage/resign.ts::parseGcsUrl exactly:
    both parse "https://storage.googleapis.com/{bucket}/{key...}"
    generically and return None for anything that doesn't match that shape,
    rather than raising or assuming a specific bucket.

    Returns None -- never raises -- for: a missing/blank value, a "Null"/
    "None" sentinel (the feedback pipeline's convention for "not set yet"),
    a URL from a different host entirely, or a URL with no bucket/key
    segment to split out. Any real, well-formed
    "https://storage.googleapis.com/{bucket}/{key...}" URL parses correctly
    regardless of which bucket it names.

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
    tap_app/api/submission.py, shared.storage.gallery_promotion, AND
    shared.jobs.gallery_promotion_sweep should all call this instead of
    reading `sub.name`/`sub["name"]` directly.

    Accepts either a Frappe Document (attribute access) or a plain dict
    (e.g. a frappe.db.sql(as_dict=True) row) -- both shapes are used across
    the call sites above, so this function supports both rather than forcing
    every caller to normalize first.

    Tries, in order:
      1. Recovering the Worker-minted id from submission_url via
         extract_object_key_from_submission_url + parse_object_key.
      2. Falling back to the Frappe autoname (sub.name / sub["name"]) --
         correct and expected for a submission whose async upload job hasn't
         populated submission_url yet (Pending/early-Processing), or whose
         submission_url never matches the expected tapapp shape (a
         non-tapapp-sourced row, or a malformed/legacy value). This is not
         an error case.

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