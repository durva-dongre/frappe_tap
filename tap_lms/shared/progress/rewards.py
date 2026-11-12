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
"""

from __future__ import annotations

import frappe

from shared.config.settings_cache import get_shared_settings
from shared.enrollment.active_batch import PROGRAM_ENROLLMENT_TABLE


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
    return get_shared_settings().points_video_complete


def points_per_quiz_correct() -> int:
    return get_shared_settings().points_per_correct_answer


def points_for_submission_first_attempt() -> int:
    return get_shared_settings().points_submission_first_attempt


def points_for_submission_review_valid() -> int:
    return get_shared_settings().points_submission_review_valid


def gems_for_submission_review_valid() -> int:
    """FIX: gems_submission_review_valid is now a real field on Shared
    Settings (tap_lms/doctype/shared_settings/shared_settings.json), so this
    reads it directly instead of falling back to a hardcoded 1 via getattr.
    The field itself still defaults to 1, preserving today's behavior for any
    site that hasn't explicitly changed it -- the difference is it's now
    genuinely configurable from the Shared Settings UI."""
    return get_shared_settings().gems_submission_review_valid


def max_submission_attempts() -> int:
    return get_shared_settings().max_submission_attempts