"""
shared/submission/rejection.py

DEPRECATED / STALE -- superseded by shared/submission/lifecycle.py's own cap
logic (check_attempt_cap / submit_artwork), which reads
Shared Settings.max_submission_attempts and Unit Progress.submission_attempts
directly. This module's can_retry() reads a `max_submission_attempts`
settings key via shared.config.settings_cache.get_int (a function that does
not exist in settings_cache.py -- see shared/config/settings_cache.py, which
only exports get_shared_settings/invalidate_config_cache/invalidate_all) and
a non-existent `attempts` field on Submission (the real field is
`submission_attempts`, and it lives on Unit Progress, not on Submission
itself).

Left unmodified and NOT wired into lifecycle.py or any new code -- kept only
because something outside this pass (possibly the whatsapp/Glific flow) may
still import it. Calling can_retry() as currently written will raise
AttributeError at the get_int call. Do not call this from new code; use
shared.submission.lifecycle.check_attempt_cap instead.
"""

from __future__ import annotations

import frappe

from shared.config.settings_cache import get_int


def can_retry(submission_name: str) -> bool:
    attempts_used = frappe.db.get_value("Submission", submission_name, "attempts") or 0
    return attempts_used < get_int("max_submission_attempts", 2)