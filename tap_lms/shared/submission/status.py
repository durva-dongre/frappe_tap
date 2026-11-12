"""
shared/submission/status.py

Closed-value helpers for a Submission doctype's own status/result_status
fields. Kept framework-free (no frappe import) so it can be unit tested and
reused by any app with the same Select option strings on its Submission
doctype (status: Pending/Processing/Completed/Failed, result_status:
Pending/Success - Original/Success - Flagged/Failed).

Two distinct eligibility definitions live here, and they are NOT the same
set of result statuses:

- is_submission_complete: whether the submission counts toward unit/track
  completion. Both "Success - Original" and "Success - Flagged" qualify --
  a flagged submission is still a completed, scored submission, not a
  failure, for the purpose of "did the student finish this unit."

- is_reward_eligible: whether the submission earns the review-valid points
  and gem. Only "Success - Original" qualifies. A flagged submission is
  deliberately excluded from reward even though it's complete -- this is
  the single gate used by the gem/point award path, kept as the one place
  that definition lives.

Call the one that matches what you're deciding. Do not use either name to
answer the other question.
"""

from __future__ import annotations

SUBMISSION_STATUS_OPTIONS = ("Pending", "Processing", "Completed", "Failed")
RESULT_STATUS_OPTIONS = ("Pending", "Success - Original", "Success - Flagged", "Failed")

COMPLETE_RESULT_STATUSES = ("Success - Original", "Success - Flagged")
REWARD_ELIGIBLE_RESULT_STATUSES = ("Success - Original",)
TERMINAL_STATUSES = ("Completed", "Failed")


def is_submission_complete(result_status: str) -> bool:
    """True iff this result status counts the submission as done for unit/
    track completion purposes. Includes flagged-but-scored submissions."""
    return result_status in COMPLETE_RESULT_STATUSES


def is_reward_eligible(result_status: str) -> bool:
    """True iff this result status earns the submission-review-valid points
    and gem. Only "Success - Original" -- a flagged submission is complete
    but not rewarded. This is the one place that gate is defined; the
    gem/point award path must call this, never is_submission_complete."""
    return result_status in REWARD_ELIGIBLE_RESULT_STATUSES


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


# Deprecated: old name, old (broader) meaning. Kept only so any existing
# caller that hasn't been migrated yet doesn't break. New code must call
# is_submission_complete or is_reward_eligible by name -- never this.
def is_valid_review_result(result_status: str) -> bool:
    return is_submission_complete(result_status)