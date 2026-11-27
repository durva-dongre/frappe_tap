"""
tap_lms/tap_app/api/config.py

New module. One whitelisted, read-only method -- get_reward_config -- backing
the Worker's GET /app/config "video"/"quiz"/"submission" reward/cap fields
(worker/src/storage/rewardConfig.ts). Mirrors every other tap_app/api/*.py
module's own convention exactly: @tap_app_method from tap_lms.tap_app.api
(the real decorator -- requires an authenticated Frappe session/API key,
maps any SharedError onto the Worker's {http_status, error_code, message}
shape, same as auth.py/events.py/profile.py/progress.py/submission.py all
already do).

This method performs NO reward computation or cap enforcement of its own --
it only reports the currently configured numbers, exactly as every other
accessor it delegates to (shared/progress/rewards.py) already does for its
own real callers (shared/progress/activities.py, shared/submission/
lifecycle.py, shared/submission/review_result.py). Each accessor already
carries its own hardcoded-default fallback for the "Shared Settings
singleton never re-saved since this field was added" gap (see that module's
own docstring) -- this endpoint adds no new fallback logic of its own, it
is a thin, read-only pass-through.

Requires only an authenticated Frappe session/API key (allow_guest=False,
via @tap_app_method) -- no additional role check, consistent with every
other tap_app/api/*.py whitelisted method in this codebase. It is read-only
and deployment-wide (not scoped to any one student), so there is nothing
student-specific to authorize beyond "the caller can reach the Worker at
all" -- the same posture mint_magic_link documents for itself in auth.py.
"""

from __future__ import annotations

from tap_lms.tap_app.api import tap_app_method
from shared.progress.rewards import (
    points_for_video,
    points_per_quiz_correct,
    points_for_submission_first_attempt,
    points_for_submission_review_valid,
    gems_for_submission_review_valid,
    max_submission_attempts,
    max_submissions_per_week,
)


@tap_app_method
def get_reward_config():
    """Worker route: GET /app/config -> FRAPPE_METHODS.getRewardConfig
    ("tap_lms.tap_app.api.config.get_reward_config"), consumed through
    worker/src/storage/rewardConfig.ts's cached wrapper (never called
    directly from a Worker handler).

    Read-only snapshot of every reward number and cap this contract
    documents as Frappe-configured (API_Reference.md §0.1). Each value
    already carries its own hardcoded-default fallback inside the
    accessor it calls -- the exact same functions submit_video_watched,
    submit_quiz, submit_artwork, and handle_review_result call directly
    for their own real point/gem/cap decisions -- so this endpoint can
    never report a number that drifts from what those write paths
    actually enforce/award.
    """
    return {
        "points_video_complete": points_for_video(),
        "points_per_correct_answer": points_per_quiz_correct(),
        "points_submission_first_attempt": points_for_submission_first_attempt(),
        "points_submission_review_valid": points_for_submission_review_valid(),
        "gems_submission_review_valid": gems_for_submission_review_valid(),
        "max_submission_attempts": max_submission_attempts(),
        "max_submissions_per_week": max_submissions_per_week(),
    }