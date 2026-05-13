"""
Tests for summer_program.scheduler

CR-003 retired `_run_grace_notifications` and `_run_reengagement` along with
the SP_Grace_Reminder and SP_Paused_Reengagement Glific flows. The previous
test suite in this file exercised those functions as Postgres-compat
regression coverage (L-002 / L-005). Both lessons are now part of the
project memory and won't regress without the lessons being reverted.

The grace-window mechanics are now covered by:
  - tests/test_grace_logic.py — T0/T14 clock arming, T5/T11 clock preservation,
    handle_grace_check expiry → t17_grace_expired
  - tests/test_cr_003_migration.py — paused_no_activity → program_dropped
    migration

The re-engagement path is gone entirely (re-engagement is now inbound-only
via SP_Incoming_Router, with the rejoin branch handled Glific-side).

This stub remains so a `bench run-tests` invocation finds the file and so
future engineers grepping for `test_scheduler` find the historical context.
"""
import unittest


class TestSchedulerRetired(unittest.TestCase):
    """Sentinel test documenting that `scheduler._run_grace_notifications`
    and `_run_reengagement` were removed in CR-003. Re-introducing them
    without the rest of the legacy grace/reminder flow would be a regression.
    """

    def test_grace_notifications_function_removed(self):
        from tap_lms.summer_program import scheduler
        self.assertFalse(
            hasattr(scheduler, "_run_grace_notifications"),
            "_run_grace_notifications was retired in CR-003. If you need "
            "weekly grace handling, see state_machine._grace_clock_updates "
            "and pe_dispatcher.handle_grace_check.",
        )

    def test_reengagement_function_removed(self):
        from tap_lms.summer_program import scheduler
        self.assertFalse(
            hasattr(scheduler, "_run_reengagement"),
            "_run_reengagement was retired in CR-003. Re-engagement is now "
            "inbound-only via the SP_Incoming_Router Glific flow; there is "
            "no proactive Frappe-side handler.",
        )
