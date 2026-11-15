"""
shared/submission/object_naming.py

Single source of truth for the tapapp object-key shape, shared by the
attempt-cap check, submission creation, and R2 promotion. Any app writing
submissions into the same bucket layout reuses this unchanged.

Key shape (must match the Worker's own storage/keys.ts byte-for-byte):
    tapapp/{assignment_id}/{student_id}/{submission_id}-{attempt}.{ext}

v9 fix -- OBJECT_KEY_RE bounds tightened to match the Worker exactly:
Previously this regex allowed assignment_id/student_id as short as 1
character (`{1,80}`) and placed no upper bound on the extension
(`[a-z0-9]+`), while the Worker's own patterns
(worker/src/storage/keys.ts::FIELD_PATTERNS, used by
assertObjectKeyMatches, and worker/src/handlers/internalHandlers.ts::
OBJECT_KEY_PATTERN, used by the nightly sweep's gallery index validation)
both require `{3,80}` for assignment_id/student_id and cap the extension
at `{1,10}`. In practice the Worker validates a client-submitted
object_key before it ever reaches Frappe, so the looser Frappe-side regex
was not independently exploitable through that path -- but a key this
regex alone would accept (a 1-2 char assignment_id/student_id, or an
absurdly long extension) could be rejected by the Worker's own
/internal/gallery/index validation if it were ever pushed there (e.g. by
a future internal job parsing keys without the Worker in front), causing
a silent mismatch between what Frappe considers a valid key and what the
Worker's own gallery indexing will accept. OBJECT_KEY_RE now matches the
Worker's FIELD_PATTERNS/OBJECT_KEY_PATTERN exactly on both bounds.

v10 fix -- build_object_key sanitizes its path-segment inputs:
assignment_id/student_id values reaching build_object_key are not
guaranteed to already be shaped like the Worker's own
[A-Za-z0-9_-]{3,80} FIELD_PATTERNS -- a legacy/WhatsApp-sourced
assignment_id such as "Spaceship Assignment-62591" contains a space,
which FIELD_PATTERNS.assignment_id (used elsewhere in this codebase for
other validation) happily allows, but which the Worker's own
OBJECT_KEY_PATTERN (worker/src/handlers/internalHandlers.ts, used to
validate every row pushed to /internal/gallery/index) rejects outright,
since that pattern's path-segment character classes never include a
space. build_object_key now runs both assignment_id and student_id
through sanitize_key_segment before building the key, so every caller
automatically produces a key that always matches the Worker's own
pattern, with no caller needing to remember to pre-sanitize its own
inputs. See sanitize_key_segment's own docstring for the exact
substitution rule and its accepted trade-offs.

v12 fix -- NEW sanitize_scope_value, for state/district/school:
The gallery's D1 scope columns (gallery_items.state/district/school) are
validated by the Worker against a DIFFERENT, stricter character class
than an object-key path segment: GALLERY_SCOPE_FIELD_PATTERNS
(worker/src/db/gallery.ts) requires /^[a-z0-9-]{2,60}$/ -- lowercase
alphanumeric and hyphen ONLY, no underscore (sanitize_key_segment, by
contrast, keeps underscores, because it targets the Worker's
OBJECT_KEY_PATTERN path-segment class, [A-Za-z0-9_-], which is a
different, looser rule for a different field).

Student.state_id / district_id / school_id are Frappe Link doc-names,
not guaranteed to already be shaped to the Worker's stricter scope-value
pattern. In particular, School.name is autonamed as
"format:{name1}-SC{#####}" (tap_lms/doctype/school/school.json), so it
can contain a literal space whenever name1 does (e.g.
"Green Valley School-SC00536"); State.name/District.name happen to BE
their own display string by autoname convention, but are not guaranteed
never to contain a space or other punctuation either (e.g.
district_id="Mumbai Suburban"). Previously these three fields were only
`.lower()`'d before being sent to the Worker's /internal/gallery/index,
with no further character sanitization -- a value like "mumbai suburban"
would pass that lower() unchanged, then fail the Worker's own
validateRow regex check, 400ing the ENTIRE batch (every row sent in that
call, not just the offending one), since the Worker inserts gallery_items
rows all-or-nothing per call (db.batch()).

sanitize_scope_value fixes this the same way sanitize_key_segment already
fixes assignment_id/student_id for the object-key path: collapse every
run of one or more disallowed characters to a single '-', so the result
always matches the Worker's own pattern regardless of what the underlying
Student Link field actually contains.

READ-PATH CAVEAT (does not fully solve the problem on its own): this
sanitizer only affects the WRITE path -- what gets stored in D1's
gallery_items.state/district/school columns. The gallery's READ-side
scope resolution (worker/src/storage/profileScope.ts::
normalizeScopeValue) applies a DIFFERENT, narrower rule: it only
lowercases and trims, it does NOT collapse spaces/punctuation the way
sanitize_scope_value does. If a student's live profile scope value
itself contains a space or other disallowed character, the Worker's own
read-side normalizeScopeValue will not match what this function wrote to
D1, because the two functions use different normalization. This
sanitizer eliminates the write-path 400; confirming school/district/state
gallery scoping continues to actually MATCH for such a student is a
separate, Worker-side concern (either teach profileScope.ts's
normalizeScopeValue the same character-collapsing rule, or ensure the
underlying doc names never contain characters outside [a-z0-9-] in the
first place).

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

# Bounds now match the Worker exactly:
#   - assignment_id / student_id: {3,80}, matching worker/src/storage/keys.ts::
#     FIELD_PATTERNS.assignment_id / FIELD_PATTERNS.student_id, and
#     worker/src/handlers/internalHandlers.ts::OBJECT_KEY_PATTERN.
#   - ext: {1,10}, matching worker/src/storage/keys.ts's filename regex
#     ([a-zA-Z0-9]{1,10}) and OBJECT_KEY_PATTERN's own [A-Za-z0-9]{1,10}.
OBJECT_KEY_RE = re.compile(
    r"^tapapp/(?P<assignment_id>[A-Za-z0-9_-]{3,80})/"
    r"(?P<student_id>[A-Za-z0-9_-]{3,80})/"
    r"(?P<submission_id>[a-z2-7]{6,16})-(?P<attempt>[1-9][0-9]?)\.(?P<ext>[a-z0-9]{1,10})$"
)

# Matches the Worker's OBJECT_KEY_PATTERN character class for the
# assignment_id/student_id path segments exactly: [A-Za-z0-9_-]. Anything
# outside this set (spaces, punctuation, unicode, etc.) is replaced with a
# single '-' by sanitize_key_segment below, so a raw, unvalidated
# assignment_id/student_id can always be safely interpolated into an R2
# object key.
_KEY_SEGMENT_DISALLOWED_CHARS = re.compile(r"[^A-Za-z0-9_-]")

# Matches the Worker's GALLERY_SCOPE_FIELD_PATTERNS character class for
# state/district/school exactly: lowercase [a-z0-9-] ONLY -- no
# underscore, unlike _KEY_SEGMENT_DISALLOWED_CHARS above, which is a
# different, looser rule for a different field (an object-key path
# segment, not a D1 gallery scope column). A RUN of one or more
# disallowed characters collapses to a SINGLE '-' (not one '-' per
# disallowed character), so "mumbai   suburban" becomes
# "mumbai-suburban", not "mumbai---suburban".
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
    """Replaces every character not in [A-Za-z0-9_-] with '-', so the
    result is always safe to interpolate into an R2/GCS object key's
    assignment_id or student_id path segment, and always matches the
    Worker's own OBJECT_KEY_PATTERN character class for that segment
    (worker/src/handlers/internalHandlers.ts).

    This exists because callers of build_object_key are not guaranteed to
    have already validated their assignment_id/student_id against the
    Worker's stricter key-segment shape. FIELD_PATTERNS.assignment_id
    (worker/src/storage/keys.ts, mirrored by shared.submission.lifecycle's
    own validation) is more permissive -- it allows a literal space -- so a
    legacy/WhatsApp-sourced assignment_id like "Spaceship Assignment-62591"
    passes that check but still contains a character the Worker's
    OBJECT_KEY_PATTERN will reject once it reaches /internal/gallery/index.
    Sanitizing once, here, at key-build time, means every caller of
    build_object_key gets a key that downstream gallery indexing will
    always accept, instead of each caller needing to remember to
    pre-sanitize its own inputs.

    Leading/trailing whitespace is stripped first, then every remaining
    disallowed character (including any interior whitespace, punctuation,
    or non-ASCII character) is replaced with a single '-'. An empty or
    falsy input is returned unchanged (there is nothing to sanitize, and
    the caller -- build_object_key -- will fail its own regex match
    downstream if an empty segment is genuinely invalid).

    NOTE: unlike sanitize_scope_value below, this replaces each
    individual disallowed character with its own '-' (so "A  B" becomes
    "A--B", not "A-B") -- kept exactly as originally shipped, since
    object-key uniqueness/collision behavior for this function is already
    relied upon elsewhere and should not change here. Collisions are an
    accepted, bounded trade-off either way: two distinct raw values that
    sanitize to the same string would collide under this scheme. This is
    no worse than the status quo for a value that previously failed to
    index at all, and is rare in practice -- assignment ids and student
    ids are not freely chosen by many independent, adversarial actors.
    """
    if not value:
        return value
    return _KEY_SEGMENT_DISALLOWED_CHARS.sub("-", value.strip())


def sanitize_scope_value(value: str | None) -> str | None:
    """Sanitizes a state/district/school value for the gallery's D1 scope
    columns, so it always matches the Worker's own
    GALLERY_SCOPE_FIELD_PATTERNS (worker/src/db/gallery.ts) exactly --
    lowercase, [a-z0-9-]{2,60} only, no underscore.

    This exists because Student.state_id / district_id / school_id are
    Frappe Link doc-names, and nothing guarantees those names are already
    shaped to the Worker's stricter scope-value pattern. School.name in
    particular is autonamed as "format:{name1}-SC{#####}"
    (tap_lms/doctype/school/school.json), so it can contain a literal
    space whenever name1 does (e.g. "Green Valley School-SC00536");
    State.name/District.name happen to BE their own display string by
    autoname convention, but are not guaranteed to be free of spaces or
    other punctuation either.

    Previously these three fields were only `.lower()`'d before being
    sent to the Worker's /internal/gallery/index, with no further
    character sanitization -- a value like "mumbai suburban" would pass
    that lower() unchanged, then be rejected outright by the Worker's own
    validateRow regex check, 400ing the WHOLE batch (every row sent in
    that call, not just the offending one), since gallery_items rows are
    inserted all-or-nothing per db.batch() call.

    Every RUN of one or more disallowed characters (anything other than
    a-z, 0-9, or '-') collapses to a SINGLE '-' (not one '-' per
    disallowed character, unlike sanitize_key_segment above) -- so
    "mumbai suburban" becomes "mumbai-suburban" and
    "Green Valley School-SC00536" becomes "green-valley-school-sc00536",
    both now valid against /^[a-z0-9-]{2,60}$/. Leading/trailing
    whitespace is stripped first (via .strip()), and any leading/trailing
    '-' left over after collapsing is stripped too, so a value that was
    entirely disallowed characters doesn't produce a bare "-" string.

    Returns None for a falsy input -- there is nothing to sanitize, and
    the caller does not need a separate `or None` at the call site (this
    function already normalizes "no real value" down to None on its own,
    whether the input was empty/None to begin with or became empty after
    stripping disallowed characters). Call sites can therefore write
    `sanitize_scope_value(student.get("state_id"))` directly.

    READ-PATH CAVEAT: this only affects the WRITE path into D1. The
    gallery's READ-side scope resolution
    (worker/src/storage/profileScope.ts::normalizeScopeValue) applies a
    DIFFERENT, narrower rule -- it only lowercases and trims, it does NOT
    collapse spaces/punctuation. If a student's live profile scope value
    itself contains a space or other disallowed character, the Worker's
    own read-side normalizeScopeValue will not produce the same string
    this function wrote to D1, so school/district/state-level gallery
    matching could still silently fail for that student even after this
    fix is applied. Confirming end-to-end scope matching for such values
    is a separate, Worker-side concern -- either teach profileScope.ts's
    normalizeScopeValue the same character-collapsing rule, or ensure the
    underlying doc names never contain characters outside [a-z0-9-] in
    the first place.
    """
    if not value:
        return None
    collapsed = _SCOPE_VALUE_DISALLOWED_CHARS.sub("-", value.strip().lower())
    stripped = collapsed.strip("-")
    return stripped or None


def build_object_key(assignment_id: str, student_id: str, submission_id: str, attempt: int, ext: str) -> str:
    """Builds the tapapp object key, sanitizing assignment_id and
    student_id first (see sanitize_key_segment) so the result always
    matches the Worker's own OBJECT_KEY_PATTERN, regardless of whether the
    caller's raw inputs already did. submission_id and ext are not
    sanitized here -- submission_id is always Worker-minted
    ([a-z2-7]{6,16}, see storage/keys.ts::mintSubmissionId) and ext is
    always resolved from a fixed, known-safe table
    (EXT_FOR_SUBMISSION_TYPE / the Worker's ACCEPTED_FORMATS_FOR), so
    neither can contain a character this function would need to clean up.
    """
    safe_assignment_id = sanitize_key_segment(assignment_id)
    safe_student_id = sanitize_key_segment(student_id)
    return f"tapapp/{safe_assignment_id}/{safe_student_id}/{submission_id}-{attempt}.{ext}"


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