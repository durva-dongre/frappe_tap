"""
hooks.py additions for Summer Program
tap_lms/summer_program/hooks_additions.py

Add these entries to your existing hooks.py file.
This file is NOT imported directly — it's a reference for what to add.

──────────────────────────────────────────────────

Add to scheduler_events in hooks.py:

    scheduler_events = {
        "daily": [
            "tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_incomplete_stages",
            "tap_lms.summer_program.scheduler.run_daily_actions",
            "tap_lms.summer_program.batch_activation.check_auto_activate",
        ],
        "cron": {
            # Per-PE dispatcher: runs every 2 minutes, picks up overdue actions
            "*/2 * * * *": [
                "tap_lms.summer_program.pe_dispatcher.dispatch_pending_actions",
            ],
            "0 */2 * * *": [
                "tap_lms.summer_program.escalation_runner.run_escalation_check",
            ],
            "0 0 * * 1": [
                "tap_lms.summer_program.batch_admin.auto_advance_batch_week",
            ],
        }
    }

──────────────────────────────────────────────────

API endpoints (auto-discovered via @frappe.whitelist):

  # ── Design-spec APIs (A1–A8) ──────────────────────────────
  tap_lms.summer_program.program_enrollment_api.get_student_state        # A1
  tap_lms.summer_program.student_progression_sp.get_weekly_content       # A2 (get_content)
  tap_lms.summer_program.save_submission.save_submission                 # A3
  tap_lms.summer_program.flow_callback.update_flow_status                # A4
  tap_lms.summer_program.reactivation.reactivate_student                 # A5
  tap_lms.summer_program.program_enrollment_api.create_program_enrollment # A6
  tap_lms.summer_program.batch_admin.update_batch_week                   # A7
  tap_lms.summer_program.program_enrollment_api.get_enrollment_summary   # A8

  # ── Admin/Dashboard APIs ──────────────────────────────────
  tap_lms.summer_program.batch_admin.admin_drop_student
  tap_lms.summer_program.api.get_bpr_status
  tap_lms.summer_program.api.list_bprs
  tap_lms.summer_program.api.get_collection_details
  tap_lms.summer_program.api.get_batch_progress
  tap_lms.summer_program.api.update_flow_ids
  tap_lms.summer_program.api.get_student_sp_status

  # ── Enrollment Pipeline ───────────────────────────────────
  tap_lms.summer_program.enrollment.start_enrollment
  tap_lms.summer_program.enrollment.setup_collections
  tap_lms.summer_program.program_enrollment_api.start_program_enrollment

  # ── Batch Activation ──────────────────────────────────────
  tap_lms.summer_program.batch_activation.validate_bpr
  tap_lms.summer_program.batch_activation.activate_bpr

  # ── Per-PE Dispatcher (scheduler cron) ─────────────────────
  tap_lms.summer_program.pe_dispatcher.dispatch_pending_actions           # cron: */2 * * * *

  # ── Legacy (from student_progression_sp.py) ───────────────
  tap_lms.summer_program.student_progression_sp.record_submission         # replaced by save_submission
  tap_lms.summer_program.student_progression_sp.get_escalation_action
  tap_lms.summer_program.student_progression_sp.get_student_sp_overview
"""
