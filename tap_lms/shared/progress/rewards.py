"""
shared/progress/rewards.py

Points/gems ledger helpers plus accessors for the reward schedule on the
shared settings singleton. Deliberately doctype-light: these functions award
against whatever enrollment-shaped row is handed to them (by name), using
direct SQL increments rather than load-mutate-save, so concurrent awards
never clobber each other and no full document load is needed on the hot path.

Gem-award policy: nothing in this module auto-awards gems on video/quiz. The
one place gems are awarded in this codebase is the feedback-review path
(shared/submission/review_result.py), which calls award_gems_for_submission
once per submission the moment its review comes back valid for the first
time. Keeping that trigger in one call site makes "where do gems come from"
auditable at a glance.

Every reward-amount accessor below falls back to a hardcoded default
instead of returning whatever Shared Settings reads back, because Shared
Settings is a Frappe Singleton ("issingle": 1): a field's `"default"` in
the doctype JSON only applies on save -- it does not retroactively
backfill a Singleton row that was never re-saved after the field was added
to the schema. On a site where the Singleton predates one of these fields
(or predates the whole doctype) and has never been opened and saved once
since, frappe.get_single(...).<field> reads back as None, not the schema
default.

This fallback is load-bearing, not cosmetic: award_points_by_name(name,
None) feeds directly into "SET points = COALESCE(points,0) + %s" with
amount=None, and Postgres NULL arithmetic sets the row's points/gems
column to NULL outright -- COALESCE only protects the LEFT side of the +,
never the right. Returning a sane int here is what keeps that arithmetic
safe; it is not optional defensive styling.

The permanent fix for the underlying gap is a migration patch that
force-saves the Shared Settings singleton once after any doctype field
addition (so defaults are actually persisted into tabSingles) -- see
shared/config/secrets_cache.py's get_magic_link_ttl for the equivalent
gap and its own fallback on that side. These fallbacks are defense in
depth underneath that migration, not a replacement for it: a site that has
correctly saved its Shared Settings at least once will never exercise
them; one that hasn't gets the documented default behavior instead of a
silently corrupted points/gems column.
"""

from __future__ import annotations

import frappe

from shared.config.settings_cache import get_shared_settings
from shared.enrollment.active_batch import PROGRAM_ENROLLMENT_TABLE

# Hardcoded fallbacks, used ONLY when the Shared Settings singleton has never
# been saved since a field was added (see module docstring). These mirror
# each field's own doctype-JSON "default" exactly, so a site that HAS saved
# its settings at least once behaves identically whether or not this
# fallback path is ever exercised.
_DEFAULT_POINTS_VIDEO_COMPLETE = 10
_DEFAULT_POINTS_PER_CORRECT_ANSWER = 1
_DEFAULT_POINTS_SUBMISSION_FIRST_ATTEMPT = 25
_DEFAULT_POINTS_SUBMISSION_REVIEW_VALID = 10
_DEFAULT_GEMS_SUBMISSION_REVIEW_VALID = 1
_DEFAULT_MAX_SUBMISSION_ATTEMPTS = 2


def award_points_by_name(program_enrollment_name: str, amount: int, bump_activity: bool = True) -> int:
    if bump_activity:
        row = frappe.db.sql(
            f"""
            UPDATE "{PROGRAM_ENROLLMENT_TABLE}"
            SET points = COALESCE(points, 0) + %s,
                last_activity_at = NOW(),
                modified = NOW()
            WHERE name = %s
            RETURNING points
            """,
            (amount, program_enrollment_name),
        )
    else:
        row = frappe.db.sql(
            f"""
            UPDATE "{PROGRAM_ENROLLMENT_TABLE}"
            SET points = COALESCE(points, 0) + %s,
                modified = NOW()
            WHERE name = %s
            RETURNING points
            """,
            (amount, program_enrollment_name),
        )
    if not row:
        frappe.throw(f"ProgramEnrollment {program_enrollment_name} not found")
    return row[0][0]


def award_gems_by_name(program_enrollment_name: str, amount: int) -> int:
    row = frappe.db.sql(
        f"""
        UPDATE "{PROGRAM_ENROLLMENT_TABLE}"
        SET gems = COALESCE(gems, 0) + %s,
            modified = NOW()
        WHERE name = %s
        RETURNING gems
        """,
        (amount, program_enrollment_name),
    )
    if not row:
        frappe.throw(f"ProgramEnrollment {program_enrollment_name} not found")
    return row[0][0]


def award_points(enrollment_doc, amount: int) -> int:
    if amount:
        enrollment_doc.points = (enrollment_doc.points or 0) + amount
    enrollment_doc.last_activity_at = frappe.utils.now_datetime()
    return enrollment_doc.points


def award_gems(enrollment_doc, amount: int) -> int:
    if amount:
        enrollment_doc.gems = (enrollment_doc.gems or 0) + amount
    return enrollment_doc.gems


def points_for_video() -> int:
    val = get_shared_settings().points_video_complete
    return val if val is not None else _DEFAULT_POINTS_VIDEO_COMPLETE


def points_per_quiz_correct() -> int:
    val = get_shared_settings().points_per_correct_answer
    return val if val is not None else _DEFAULT_POINTS_PER_CORRECT_ANSWER


def points_for_submission_first_attempt() -> int:
    val = get_shared_settings().points_submission_first_attempt
    return val if val is not None else _DEFAULT_POINTS_SUBMISSION_FIRST_ATTEMPT


def points_for_submission_review_valid() -> int:
    val = get_shared_settings().points_submission_review_valid
    return val if val is not None else _DEFAULT_POINTS_SUBMISSION_REVIEW_VALID


def gems_for_submission_review_valid() -> int:
    """gems_submission_review_valid is a real field on Shared Settings
    (tap_lms/doctype/shared_settings/shared_settings.json). Reads it
    directly, falling back to the documented default of 1 only if the
    singleton has never been saved since the field was added (see module
    docstring) -- this is defense in depth, not a replacement for actually
    saving Shared Settings once post-deploy."""
    val = get_shared_settings().gems_submission_review_valid
    return val if val is not None else _DEFAULT_GEMS_SUBMISSION_REVIEW_VALID


def max_submission_attempts() -> int:
    val = get_shared_settings().max_submission_attempts
    return val if val is not None else _DEFAULT_MAX_SUBMISSION_ATTEMPTS