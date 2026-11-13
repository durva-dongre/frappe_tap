"""
tap_lms/tap_app/api/submission.py

Worker-facing wrappers for the submission-read routes (submission.list,
submission.get) and submit_artwork. Every submission-shaped response this
file produces carries `submission_id` as the sole identifier -- never a
bare `name` field -- matching API_Reference.md's and the Worker
contract's documented shape for submit_artwork, submission.list, and
submission.get alike. `name` (Frappe's own document name) is the same
value under the hood for this source, but is deliberately not exposed as
a second key: one canonical identifier field name removes a class of
client-side bugs where the wrong field gets read for the same underlying
value. A submission's numeric mark is returned as `points`, not `score` --
Submission.grade is the underlying stored field, but the wire key name
matches points_total/points_awarded/points_tier elsewhere in this API, so
a client never has to remember a different vocabulary for a submission's
mark versus its other point-shaped fields. `points` can be JSON null for
an ungraded submission (Submission.grade is nullable); the Worker's
util/errors.ts::ok() preserves null values deliberately (only `undefined`
keys are stripped), so this reaches the app as a real null, not an absent
key or a 0 -- treat it like the other documented nullable fields in
API_Reference.md §0.1.

Deliberately NO points_awarded/gems_awarded on list/get: submission.list
and submission.get are plain, ungated historical reads -- there is no
"have you already seen this" concept here the way there is on
/progress/sync and /progress/last_submission (which are gated by an
updated_at/last_updated epoch comparison, so a given award is reported at
most once per epoch advance). A one-time-award field on an ungated read
would be reported again on every page view of submission history,
forever. The only places points_awarded/gems_awarded belong are
/progress/sync's and /progress/last_submission's last_submission payload
(see shared/profile/sync.py, which documents the epoch gating in full).

submit_artwork takes `object_key` -- the exact value request_upload issued
and the Worker already confirmed exists, has the right size, and has the
right content-type on GCS before ever calling here (see
worker/src/handlers/submissionHandlers.ts::submitArtwork). This thin
wrapper's only transformation is:

    object_key  ->  plain public GCS URL  ->  submission_url

passed straight into shared.submission.lifecycle.submit_artwork, whose own
signature (student_id, assignment_id, submission_url, context) and
downstream call into tap_lms.imgana.submission.submit_artwork are both
unaffected by this file. Neither imgana nor feedback_handler/
feedback_consumer.py needs any awareness of object_key at all.

GCS bucket used to build the URL: Shared Settings.gcs_bucket, via
get_gcs_credentials()["bucket"] (shared/config/secrets_cache.py). This
must be configured to the same bucket as the Worker's own
GCS_AUTHENTICATED_BUCKET (`"tap-submission"` in worker/wrangler.toml) --
if the two ever disagree, the URL built here points at a different bucket
than the one the Worker's signed PUT actually wrote to, and the object
will 404 on Frappe's own submission record. This is an infrastructure
precondition to verify in Shared Settings, not something this code can
detect or correct for on its own.

idempotency_key is accepted here and ignored: the Worker already wraps the
whole call in its own Cache-API-backed idempotency layer
(cache/idempotency.ts::withIdempotency), keyed by (route, student_id,
idempotency_key) -- Frappe never needs to dedupe this call itself.

_resolve_submission_context can return None when no Unit Progress row can
be found for a submission (a data-integrity gap, not the common case).
get_submission logs a warning whenever a context filter is requested
against a submission whose context could not be resolved at all, so that
gap stays visible in Frappe's own logs; the wire response in that case is
still NotFound either way, per API_Reference.md §4.4's documented "exists
but not under the context filter given" case -- an unresolvable context is
a subset of that case, not a new one the client needs to distinguish, so
the logging is purely for operability and changes nothing on the wire.

Untouched and out of scope for this file: context resolution via Unit
Progress rows, assignment_id_link's fallback to assign_id for legacy
WhatsApp-sourced submissions, and updated_at's derivation from
Submission.modified -- all already correct and unrelated to the
identifier/field-naming concerns this file is responsible for.
"""

from __future__ import annotations

import frappe

from tap_lms.tap_app.api import tap_app_method
from shared.submission.lifecycle import check_attempt_cap as _check_attempt_cap
from shared.submission.lifecycle import submit_artwork as _submit_artwork
from shared.config.secrets_cache import get_gcs_credentials
from shared.progress.unit_progress import (
    attempt_info_for_submission,
    find_unit_progress_row_for_submission,
)
from shared.errors import InvalidInput, NotFound


@tap_app_method
def check_attempt_cap(student_id: str, assignment_id: str, context: str = "program"):
    return _check_attempt_cap(student_id, assignment_id, context)


def _build_submission_url_from_object_key(object_key: str) -> str:
    """The one place `object_key -> plain public GCS URL` conversion happens
    for the submit_artwork path. Mirrors exactly what the Worker's own
    publicHttpsUrl()/signV4Url() build the URL shape from
    (worker/src/storage/gcs.ts): https://storage.googleapis.com/{bucket}/{key}.

    Does not URL-encode path segments here the way the Worker's publicHttpsUrl
    does (encodeURIComponent per segment) -- object_key is already validated
    upstream by the Worker against a fixed, URL-safe character set
    (storage/keys.ts::FIELD_PATTERNS / parseObjectKey: [A-Za-z0-9_-] plus a
    literal "/", "-", "."), so no character in a legitimately-issued
    object_key ever needs escaping. If object_key is missing/blank, this is
    an INVALID_INPUT from this wrapper, not a 500 from a malformed URL
    reaching imgana.
    """
    if not object_key or not isinstance(object_key, str):
        raise InvalidInput("object_key missing")

    bucket = get_gcs_credentials().get("bucket")
    if not bucket:
        frappe.throw(
            "Shared Settings.gcs_bucket is not configured; cannot build a "
            "submission URL from object_key",
        )

    return f"https://storage.googleapis.com/{bucket}/{object_key}"


@tap_app_method
def submit_artwork(
    student_id: str,
    assignment_id: str,
    object_key: str,
    context: str = "program",
    idempotency_key: str | None = None,
):
    """Worker route: POST /submission/submit_artwork -> FRAPPE_METHODS.submitArtwork.

    object_key is the exact value the Worker's /submission/request_upload
    issued and the app PUT its file to (API_Reference.md §4.1-4.2). The
    Worker has already confirmed the object's existence, size, and
    content-type on GCS before calling us.

    We build the plain public GCS URL from object_key here, in this thin
    wrapper only, so that shared.submission.lifecycle.submit_artwork --
    and, underneath it, imgana's submit_artwork pipeline -- keep taking a
    plain submission_url exactly as before. idempotency_key is accepted
    and ignored, since the Worker already dedupes this call itself
    (cache/idempotency.ts::withIdempotency).

    This function's return value comes straight from
    shared.submission.lifecycle.submit_artwork, whose own docstring is the
    authority on what that return shape contains and why.
    """
    submission_url = _build_submission_url_from_object_key(object_key)

    return _submit_artwork(
        student_id=student_id,
        assignment_id=assignment_id,
        submission_url=submission_url,
        context=context,
    )


def _resolve_submission_context(submission_name: str) -> str | None:
    """Resolves which track ("program" | "event") a submission belongs to,
    via the Unit Progress row it's linked from. Returns None if no such row
    can be found (e.g. data integrity gap) -- callers treat that as "unknown
    context", not as an error, except get_submission's explicit filter case
    where an unresolvable context simply can't match a requested filter."""
    row = find_unit_progress_row_for_submission(submission_name)
    return row["unit_type"] if row else None


def _resolve_updated_at_epoch(sub) -> int:
    """The one place `updated_at` is computed for a submission wire shape.
    Prefers Frappe's own `modified` timestamp (maintained automatically on
    every save -- including every grading-pipeline update), which is the
    correct "last updated" signal. Falls back to `created_at` only if
    `modified` is somehow unavailable."""
    modified = getattr(sub, "modified", None)
    if modified:
        return int(modified.timestamp())
    created_at = getattr(sub, "created_at", None)
    if created_at:
        return int(created_at.timestamp())
    return 0


def _resolve_assignment_id_link(sub) -> str | None:
    """Falls back to `assign_id` when `assignment_id_link` is empty --
    covers older/legacy WhatsApp-sourced submissions where only `assign_id`
    was ever populated."""
    link = getattr(sub, "assignment_id_link", None)
    if link:
        return link
    return getattr(sub, "assign_id", None)


def _submission_wire_shape(sub, attempt_number: int, attempts_remaining: int, context: str | None = None) -> dict:
    """Aligned with the Worker's RawSubmission shape (worker/src/storage/
    resign.ts) and API_Reference.md §3.3/§3.4/§4.3/§4.4. view_url and
    overall_feedback_audio_url are sent as the submission's own stored,
    already-resolved URLs (Submission.submission_url /
    Submission.audio_feedback_url) -- whichever GCS bucket they actually
    live in. This is deliberate: the Worker's storage/resign.ts::
    resolveMediaUrl parses ANY "https://storage.googleapis.com/{bucket}/{key}"
    URL generically, with no bucket allowlist, and signs a fresh GET URL
    against whichever bucket the URL actually names. Never object_key/
    media_location here -- only the signed-ready view_url /
    overall_feedback_audio_url, per the contract's "no raw storage key on
    any read" rule.

    `context` is resolved by the caller (list_submissions/get_submission)
    via _resolve_submission_context, since that resolution is already paid
    for once per row alongside attempt_info_for_submission and shouldn't be
    duplicated inside this shaping function.

    Identifier: only `submission_id` -- no bare `name` key anywhere in this
    shape. `sub.name` (Frappe's own document name) is read internally to
    populate submission_id but is never itself a separate response key.

    Score/mark: returned as `points` (not `score`). See module docstring
    for why. `points` can be JSON null for an ungraded submission -- this
    is a real, intentional value, not a bug.

    Deliberately no points_awarded/gems_awarded here -- see module
    docstring. This is a plain historical read; one-time grading-bonus
    notification fields belong only on /progress/sync and
    /progress/last_submission's last_submission payload.
    """
    return {
        "submission_id": sub.name,
        "assignment_id_link": _resolve_assignment_id_link(sub),
        "status": sub.status,
        "result_status": sub.result_status,
        "view_url": sub.submission_url,
        "points": sub.grade,
        "overall_feedback_translated": sub.overall_feedback_translated,
        "overall_feedback_audio_url": sub.audio_feedback_url,
        "attempt_number": attempt_number,
        "attempts_remaining": attempts_remaining,
        "context": context,
        "created_at": sub.created_at.isoformat() if getattr(sub, "created_at", None) else None,
        "updated_at": _resolve_updated_at_epoch(sub),
    }


@tap_app_method
def list_submissions(student_id: str):
    rows = frappe.get_all(
        "Submission",
        filters={"student_id": student_id},
        fields=["name", "assign_id", "assignment_id_link", "status", "result_status",
                "submission_url", "grade", "overall_feedback_translated",
                "audio_feedback_url", "created_at", "modified"],
        order_by="created_at desc",
    )
    out = []
    for r in rows:
        attempt_number, attempts_remaining = attempt_info_for_submission(r.name)
        context = _resolve_submission_context(r.name)
        out.append(_submission_wire_shape(r, attempt_number, attempts_remaining, context))
    return {"submissions": out, "count": len(out), "total_count": len(out), "has_more": False}


@tap_app_method
def get_submission(student_id: str, submission_id: str, context: str | None = None):
    try:
        sub = frappe.get_doc("Submission", submission_id)
    except frappe.DoesNotExistError:
        raise NotFound()
    if sub.student_id != student_id:
        raise NotFound()

    actual_context = _resolve_submission_context(submission_id)

    if context:
        if actual_context is None:
            # A context filter was requested but this submission's own
            # context could not be resolved at all (no matching Unit
            # Progress row -- a data-integrity gap, not a genuine context
            # mismatch). The wire response is unchanged (still NotFound,
            # per API_Reference.md §4.4's documented "exists but not under
            # the context filter given" case) -- logged distinctly from an
            # ordinary mismatch so the underlying data gap is visible in
            # Frappe's own logs instead of looking indistinguishable from
            # the student simply asking for the wrong track.
            frappe.logger().warning(
                f"get_submission: context filter {context!r} requested for "
                f"submission {submission_id}, but its own context could not "
                f"be resolved (no matching Unit Progress row found) -- "
                f"returning NotFound per contract, but this indicates a "
                f"possible data-integrity gap, not necessarily a genuine "
                f"context mismatch."
            )
            raise NotFound()
        if actual_context != context:
            raise NotFound()

    attempt_number, attempts_remaining = attempt_info_for_submission(submission_id)
    return _submission_wire_shape(sub, attempt_number, attempts_remaining, actual_context)