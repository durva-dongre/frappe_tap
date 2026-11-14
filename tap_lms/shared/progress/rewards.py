"""
shared/progress/rewards.py

Points/gems ledger helpers plus accessors for the reward schedule on the
shared settings singleton. Deliberately doctype-light: these functions
award against whatever enrollment-shaped row is handed to them (by name),
using direct SQL increments rather than load-mutate-save, so concurrent
awards never clobber each other and no full document load is needed on
the hot path.

Gem-award policy: nothing in this module auto-awards gems on video/quiz.
The one place gems are awarded in this codebase is the feedback-review
path (shared/submission/review_result.py), which calls
award_gems_for_submission once per submission the moment its review comes
back valid for the first time. Keeping that trigger in one call site makes
"where do gems come from" auditable at a glance.

SINGLETON-DEFAULT GAP
----------------------
Every reward-amount accessor below falls back to a hardcoded default
instead of returning whatever Shared Settings reads back, because Shared
Settings is a Frappe Singleton ("issingle": 1): a field's `"default"` in
the doctype JSON only applies on save -- it does not retroactively
backfill a Singleton row that was never re-saved after the field was
added to the schema. On a site where the Singleton predates one of these
fields (or predates the whole doctype) and has never been opened and
saved once since, frappe.get_single(...).<field> reads back as None, not
the schema default.

This fallback is load-bearing, not cosmetic: award_points_by_name(name,
None) feeds directly into "SET points = COALESCE(points,0) + %s" with
amount=None, and Postgres NULL arithmetic sets the row's points/gems
column to NULL outright -- COALESCE only protects the LEFT side of the +,
never the right. Returning a sane int here is what keeps that arithmetic
safe; it is not optional defensive styling.

max_submissions_per_week() follows this exact same pattern: it is the
weekly submission cap (shared/submission/lifecycle.py::submit_artwork
checks ProgramEnrollment.submission_this_week against it before accepting
a new attempt, raising CapReached/CONFLICT if the cap is already reached).
Its fallback (1000) mirrors Shared Settings.max_submissions_per_week's own
doctype-JSON default exactly, for the same "singleton never re-saved"
reason as every other accessor in this file.

The permanent fix for the underlying gap is a migration patch that
force-saves the Shared Settings singleton once after any doctype field
addition (so defaults are actually persisted into tabSingles) -- see
shared/config/secrets_cache.py's get_magic_link_ttl for the equivalent gap
and its own fallback on that side. These fallbacks are defense in depth
underneath that migration, not a replacement for it: a site that has
correctly saved its Shared Settings at least once will never exercise
them; one that hasn't gets the documented default behavior instead of a
silently corrupted points/gems column.

LAST_ACTIVITY_AT POLICY
-------------------------
award_points() and award_points_by_name() do NOT bump last_activity_at
unconditionally. The goal: last_activity_at (and therefore sync's
"has anything changed" check) should advance only when a SUBMISSION
updates -- so a plain video watch or quiz attempt does not, on its own,
cause sync to report changed: true for the submission-related fields it
was never meant to signal.

The caller decides, explicitly, whether an activity counts as a
last_activity_at-worthy event by passing bump_activity=True:
  - shared/progress/activities.py (submit_video_watched, submit_quiz):
    call award_points(doc, amount, bump_activity=False) -- video/quiz
    activity awards points but does NOT advance last_activity_at.
  - shared/submission/lifecycle.py (submit_artwork): calls
    award_points(pe, points_awarded, bump_activity=True) on every
    successful attempt (first or reattempt) -- see that module's
    Decision D docstring.
  - shared/submission/review_result.py: continues to bump
    last_activity_at directly via frappe.db.set_value on its own
    reward/completion branches -- both are submission-outcome events,
    unaffected by this policy.

award_points_by_name's bump_activity parameter has always existed with
this meaning; award_points (the doc-mutating variant) carries the same
parameter for parity.
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
_DEFAULT_MAX_SUBMISSIONS_PER_WEEK = 1000


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


def award_points(enrollment_doc, amount: int, bump_activity: bool = True) -> int:
    """Adds `amount` (may be 0) to enrollment_doc.points, in memory --
    caller is responsible for saving the doc, exactly as before.

    bump_activity controls whether enrollment_doc.last_activity_at is also
    advanced to now(), in memory, as part of this same call:
      - bump_activity=True (submission-outcome callers, e.g.
        shared/submission/lifecycle.py::submit_artwork on every successful
        attempt, first or reattempt -- see that module's Decision D):
        last_activity_at is always bumped, even when amount is 0 (a
        reattempt earns no points but must still advance last_activity_at
        so sync's changed-detection sees it).
      - bump_activity=False (video/quiz activity callers, e.g.
        shared/progress/activities.py::submit_video_watched/submit_quiz):
        points are still added as before, but last_activity_at is left
        untouched -- a plain video watch or quiz attempt does not, on its
        own, advance the enrollment's last_activity_at or trigger sync's
        "something changed" signal. See module docstring for the full
        policy.

    Defaults to True (bump) to match the historical behavior for any
    caller that doesn't pass this explicitly -- but every caller in this
    codebase now passes it explicitly; see module docstring for the full
    list.
    """
    if amount:
        enrollment_doc.points = (enrollment_doc.points or 0) + amount
    if bump_activity:
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


def max_submissions_per_week() -> int:
    """Weekly cap on graded submission reviews per student, program
    context only (Shared Settings.max_submissions_per_week). Checked by
    shared/submission/lifecycle.py::submit_artwork against
    ProgramEnrollment.submission_this_week before accepting a new attempt
    -- a student at or over this cap is rejected with CapReached
    (CONFLICT), the same error used for the existing per-assignment
    attempt cap, but this is a separate, weekly, cross-assignment cap.
    Falls back to the documented default (1000 -- deliberately high, so
    the cap is a practical no-op until an operator lowers it) only if the
    singleton has never been saved since this field was added -- same
    "singleton never re-saved" reasoning as every other accessor in this
    module; see module docstring.

    NOTE: this cap is checked at SUBMIT time against a counter
    (submission_this_week) that is only incremented at GRADE time (see
    shared/submission/review_result.py). Because grading is asynchronous,
    rapid resubmission before earlier attempts finish grading can submit
    past this cap before the counter catches up -- the cap is a practical
    deterrent, not a hard guarantee against burst submission. This is a
    known, accepted limitation of checking a counter that free-runs ahead
    of its own increment site; tightening it (e.g. counting in-flight
    Pending/Processing submissions too) is a deliberate follow-up, not
    done here.
    """
    val = get_shared_settings().max_submissions_per_week
    return val if val is not None else _DEFAULT_MAX_SUBMISSIONS_PER_WEEK