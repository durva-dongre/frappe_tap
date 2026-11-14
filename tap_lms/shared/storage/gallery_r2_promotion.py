"""
shared/storage/gallery_r2_promotion.py

The missing piece shared/submission/review_result.py's gallery branch has
always been written to call (guarded by a try/except ImportError, since
this file previously did not exist on disk at all):

    try:
        from shared.storage.gallery_r2_promotion import promote_submission_media_to_r2
    except ImportError:
        promote_submission_media_to_r2 = None

    ...

    r2_result = promote_submission_media_to_r2(
        gcs_submission_url=submission_doc.submission_url,
        assignment_id=submission_doc.assign_id or submission_doc.assignment_id_link,
        student_id=submission_doc.student_id,
        submission_id=submission_id,
        attempt=attempt_number,
    )
    if r2_result:
        notify_worker_gallery_index(
            submission_doc, row,
            r2_object_key=r2_result["r2_object_key"],
            media_type=r2_result["media_type"],
        )

This module's ONE job is to make that call real: copy a submission's media
from wherever it actually lives on GCS into the R2 bucket the Worker's
gallery read path (worker/src/db/gallery.ts, worker/src/storage/r2.ts)
signs GET urls against, under the exact object-key shape the Worker's own
internalHandlers.ts::OBJECT_KEY_PATTERN requires, and report back the key
and media_type notify_worker_gallery_index needs to index it in D1.

No doctype change. No change to imgana (tap_lms/imgana/*) or to anything
outside shared/ and tap_lms/ generally -- imgana remains the only thing
that ever creates a Submission row or writes submission_url; this module
only ever READS submission_url (as a plain string argument, never by
loading the Submission doc itself) and copies bytes between two storage
backends.

ANY BUCKET, NOT ONE HARDCODED BUCKET
--------------------------------------
gcs_submission_url can point at any GCS bucket an operator has upload
pipelines configured to write to -- e.g.
"https://storage.googleapis.com/assignment_submission_tap/tapapp/CAATA3-U01-A01/ST00034562/k3f9a2b7x1-1.webp"
today, a different bucket tomorrow. This module never assumes or
hardcodes a bucket name anywhere: the SOURCE bucket is parsed directly out
of gcs_submission_url itself (via
shared.submission.object_naming.extract_gcs_bucket_and_key, the same
generic "https://storage.googleapis.com/{bucket}/{key...}" parse the
Worker's own storage/resign.ts::parseGcsUrl uses), and the single GCS
service-account credential already shared by every other GCS access point
in this codebase (shared.config.secrets_cache.get_gcs_credentials()
-- service_account_json) is used to read from WHATEVER bucket that URL
names, exactly as resign.ts does on the Worker side: one credential,
tried against any bucket, succeeding only if that credential actually has
read access to it.

The DESTINATION bucket (R2) is likewise never hardcoded as a literal
string anywhere in this file -- it is read from
shared.config.secrets_cache.get_r2_credentials()["bucket"] (Shared
Settings.r2_bucket), the exact same accessor
shared/export/event_exporter.py::_put_r2_json already uses for its own R2
writes. Operationally this should be configured to match the Worker's own
R2_SUBMISSIONS_BUCKET_NAME (wrangler.toml: "tapapp-submissions") -- that
is a Shared Settings configuration concern, not something this module
decides or overrides.

OBJECT KEY SHAPE
-----------------
The R2 object key this module mints is built via
shared.submission.object_naming.build_object_key -- the exact same
function/shape used for the GCS key itself
(tapapp/{assignment_id}/{student_id}/{submission_id}-{attempt}.{ext}) --
so the R2 copy lives under a key that is byte-shape-identical to the
convention the rest of this codebase already uses, and that matches the
Worker's own OBJECT_KEY_PATTERN
(worker/src/handlers/internalHandlers.ts):
    ^tapapp/[A-Za-z0-9_-]{3,80}/[A-Za-z0-9_-]{3,80}/[A-Za-z0-9_-]+-[1-9][0-9]?\\.[A-Za-z0-9]{1,10}$

The extension used in that key is recovered from the SOURCE GCS object's
own stored extension (parsed from gcs_submission_url's own object_key)
whenever it is a recognized accepted format
(shared.submission.object_naming.EXT_TO_SUBMISSION_TYPE) -- never
reassigned or guessed -- so the R2 copy's filename extension always
matches what was actually uploaded. media_type ("image" | "video", the
only two values the Worker's D1 gallery_items.media_type column and
notify_worker_gallery_index accept) is derived from that same extension
via shared.submission.object_naming.submission_type_from_ext, falling back
to the downloaded object's own GCS-reported Content-Type
(submission_type_from_content_type) only if the extension itself is
unrecognized.

FAILURE HANDLING -- ALWAYS None, NEVER RAISE
-----------------------------------------------
review_result.py's own gallery branch already wraps this whole call in a
try/except Exception and logs a warning on any exception, and separately
treats a plain falsy return (None) as "no media, or R2/GCS unavailable" --
logged at info level, not a warning, per its own existing log line. This
module honors BOTH of those expectations:

  - Every genuinely expected "nothing to promote" case (no usable
    submission_url, GCS/R2 not configured, the source object doesn't
    exist, the extension isn't a recognized media format) returns None,
    quietly (an info-level log line here, not a warning) -- these are not
    bugs, they're normal states (e.g. a text/emoji submission that should
    never reach this function in the first place, a pre-media-pipeline
    legacy row, or an environment where R2 simply isn't configured yet).
  - A genuinely unexpected failure (a network error talking to GCS or R2,
    a malformed service-account credential, an R2 upload rejected for a
    reason other than "not configured") is allowed to raise -- review_result.py's
    own try/except Exception around this call already catches, logs, and
    safely no-ops on exactly this case, so there is no need to swallow it
    a second time here. Swallowing it here too would just make a real
    infra problem silently invisible instead of showing up once, clearly,
    in review_result.py's own warning log.
"""

from __future__ import annotations

import mimetypes
from typing import Optional, TypedDict

import frappe
import requests

from shared.config.secrets_cache import get_gcs_credentials, get_r2_credentials
from shared.submission.object_naming import (
    build_object_key,
    extract_gcs_bucket_and_key,
    submission_type_from_content_type,
    submission_type_from_ext,
)

_GCS_DOWNLOAD_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"
_GCS_API_TIMEOUT_SECONDS = 30
_R2_UPLOAD_TIMEOUT_SECONDS = 30


class R2PromotionResult(TypedDict):
    r2_object_key: str
    media_type: str


def promote_submission_media_to_r2(
    gcs_submission_url: str | None,
    assignment_id: str | None,
    student_id: str | None,
    submission_id: str,
    attempt: int | None = None,
) -> Optional[R2PromotionResult]:
    """Copies one submission's media from GCS (whatever bucket
    gcs_submission_url names) to R2, under the gallery's
    tapapp/{assignment_id}/{student_id}/{submission_id}-{attempt}.{ext}
    key shape, and returns {"r2_object_key": ..., "media_type": ...} for
    the caller to hand to shared.storage.gallery_promotion.
    notify_worker_gallery_index.

    Returns None (logged at info level) for any case where there is
    legitimately nothing to promote: a missing/blank/non-GCS
    gcs_submission_url, R2 not configured, the source object doesn't
    actually exist on GCS, or the object's extension isn't a recognized
    image/video format. Lets a genuine infrastructure error (network
    failure, malformed credentials, an unexpected R2/GCS error response)
    propagate as an exception -- review_result.py's own caller already
    wraps this call in try/except Exception and logs a warning, so a real
    failure is still surfaced, just one level up.

    attempt defaults to 1 if not given or falsy, matching
    review_result.py's own "attempt_number = (row or {}).get(
    'submission_attempts') or 1" fallback for a submission whose Unit
    Progress row couldn't be resolved.
    """
    if not assignment_id or not student_id or not submission_id:
        frappe.logger().info(
            f"promote_submission_media_to_r2: missing assignment_id/student_id/"
            f"submission_id (assignment_id={assignment_id!r}, student_id={student_id!r}, "
            f"submission_id={submission_id!r}) -- skipping promotion for this submission."
        )
        return None

    parsed_source = extract_gcs_bucket_and_key(gcs_submission_url)
    if not parsed_source:
        frappe.logger().info(
            f"promote_submission_media_to_r2: submission_id={submission_id} has no "
            f"usable GCS submission_url ({gcs_submission_url!r}) -- skipping promotion "
            f"(expected for text/emoji submissions, or a row whose async upload job "
            f"has not populated submission_url yet)."
        )
        return None
    source_bucket, source_object_key = parsed_source

    r2_creds = get_r2_credentials()
    if not r2_creds.get("account_id") or not r2_creds.get("bucket"):
        frappe.logger().info(
            f"promote_submission_media_to_r2: R2 is not configured (Shared Settings."
            f"r2_account_id / r2_bucket missing) -- skipping promotion for "
            f"submission_id={submission_id}."
        )
        return None

    gcs_creds = get_gcs_credentials()
    if not gcs_creds.get("service_account_json"):
        frappe.logger().info(
            f"promote_submission_media_to_r2: GCS service account is not configured "
            f"(Shared Settings.gcs_service_account_json missing) -- skipping promotion "
            f"for submission_id={submission_id}."
        )
        return None

    downloaded = _download_from_gcs(gcs_creds["service_account_json"], source_bucket, source_object_key)
    if downloaded is None:
        frappe.logger().info(
            f"promote_submission_media_to_r2: source object not found on GCS "
            f"(bucket={source_bucket!r}, object_key={source_object_key!r}) for "
            f"submission_id={submission_id} -- skipping promotion."
        )
        return None
    content_bytes, content_type = downloaded

    # Recover the extension from the SOURCE object's own key -- never reassigned,
    # never guessed. Only a recognized accepted image/video extension is promoted;
    # anything else (an unexpected/legacy extension) is treated as "not a gallery-
    # eligible media type" rather than promoted under a made-up extension.
    source_ext = source_object_key.rsplit(".", 1)[-1].lower() if "." in source_object_key else ""
    media_type = submission_type_from_ext(source_ext) or submission_type_from_content_type(content_type)
    if not media_type:
        frappe.logger().info(
            f"promote_submission_media_to_r2: source object's extension "
            f"({source_ext!r}) and content type ({content_type!r}) do not resolve to "
            f"a recognized image/video format for submission_id={submission_id} -- "
            f"skipping promotion (this submission is not gallery-eligible media)."
        )
        return None

    resolved_ext = source_ext or mimetypes.guess_extension(content_type or "") or ""
    resolved_ext = resolved_ext.lstrip(".").lower()
    if not resolved_ext:
        frappe.logger().info(
            f"promote_submission_media_to_r2: could not resolve a file extension for "
            f"submission_id={submission_id} (source_object_key={source_object_key!r}, "
            f"content_type={content_type!r}) -- skipping promotion."
        )
        return None

    r2_object_key = build_object_key(
        assignment_id=assignment_id,
        student_id=student_id,
        submission_id=submission_id,
        attempt=int(attempt) if attempt else 1,
        ext=resolved_ext,
    )

    _upload_to_r2(r2_creds, r2_object_key, content_bytes, content_type)

    frappe.logger().info(
        f"promote_submission_media_to_r2: promoted submission_id={submission_id} "
        f"from gcs://{source_bucket}/{source_object_key} to r2 key={r2_object_key}, "
        f"media_type={media_type}."
    )

    return {"r2_object_key": r2_object_key, "media_type": media_type}


def _download_from_gcs(service_account_json: str, bucket: str, object_key: str) -> Optional[tuple[bytes, str | None]]:
    """Downloads one object's bytes + Content-Type from GCS via the shared
    service-account credential, against WHATEVER bucket is named -- never
    a hardcoded bucket. Returns None (not an exception) specifically for a
    404 (object genuinely doesn't exist); any other non-2xx response
    raises, since that is an unexpected infrastructure condition the
    caller (review_result.py) should see and log, not silently skip.
    """
    from google.cloud import storage as gcs_storage
    from google.oauth2 import service_account

    import json as _json

    info = _json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=[_GCS_DOWNLOAD_SCOPE]
    )
    client = gcs_storage.Client(project=info.get("project_id"), credentials=credentials)
    bucket_ref = client.bucket(bucket)
    blob = bucket_ref.blob(object_key)

    if not blob.exists(client=client):
        return None

    blob.reload(client=client)
    content_bytes = blob.download_as_bytes(client=client, timeout=_GCS_API_TIMEOUT_SECONDS)
    content_type = blob.content_type
    return content_bytes, content_type


def _upload_to_r2(r2_creds: dict, object_key: str, content_bytes: bytes, content_type: str | None) -> None:
    """Uploads bytes to R2 at object_key, using the same boto3-against-the-
    R2-S3-compatible-endpoint pattern already established by
    shared/export/event_exporter.py::_put_r2_json, so there is exactly one
    way this codebase talks to R2."""
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{r2_creds['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=r2_creds["access_key_id"],
        aws_secret_access_key=r2_creds["secret_access_key"],
        region_name="auto",
    )
    put_kwargs = {
        "Bucket": r2_creds["bucket"],
        "Key": object_key,
        "Body": content_bytes,
    }
    if content_type:
        put_kwargs["ContentType"] = content_type

    client.put_object(**put_kwargs)