from . import __version__ as app_version


app_name = "tap_lms"
app_title = "Tap Lms"
app_publisher = "Techt4dev"
app_description = "Lms system for tap"
app_email = "tech4dev@gmail.com"
app_license = "MIT"


# Document Events
doc_events = {
    "School": {
        "before_save": "tap_lms.tap_lms.doctype.school.school.before_save"
    },
    "Teacher": {
        "on_update": "tap_lms.glific_webhook.update_glific_contact"
    },
    "StudentStageProgress": {
        "after_insert": "tap_lms.tap_lms.doctype.studentonboardingprogress.studentonboardingprogress.update_student_progress",
        "on_update": "tap_lms.tap_lms.doctype.studentonboardingprogress.studentonboardingprogress.update_student_progress"
    },
    # CR-002 v2 gamification (2026-05-13): VideoClass completion via
    # StudentContentLog drives the activity-points handler. The handler also
    # arms the grace clock on the first VideoClass of each week (CR-003
    # follow-up 2: atomic Postgres CASE WHEN on `weekly_video_done`). Without
    # this hook the activity-points pipeline AND the grace clock are dead.
    "StudentContentLog": {
        "after_insert": "tap_lms.summer_program.activity_points.handle_content_log"
    },
    # CR-002 v2 gamification (2026-05-13): quiz attempts award per-question
    # points (correct → q.points; wrong → q.failed_points). The handler is
    # idempotent via `attempt.points_earned` so re-saves of completed
    # attempts are no-ops.
    "StudentQuizAttempt": {
        "on_update": "tap_lms.summer_program.quiz_points.handle_attempt_update"
    }
}

# Scheduled Tasks
#
# Daily:
#   - update_incomplete_stages: legacy onboarding sweep (pre-existing)
#   - run_daily_actions: SP daily housekeeping (scheduler.py)
#   - check_auto_activate: SP — auto-activates BPRs whose batch.start_date has
#                          arrived; seeds next_action_at on PEs so the per-PE
#                          dispatcher has work. See task #19 for details.
#   - run_nightly_window_maintenance: Citizenship Academy (Tapapp) — merged
#                          replacement for the former run_window_rollover +
#                          run_tapapp_xp_window_rotate pair. Both jobs touched
#                          overlapping Tapapp Learner columns (window_start_date,
#                          streak, xp rotation) with no shared guard, so a cron
#                          overlap or manual retrigger could race the two
#                          against each other. This single job takes one lock,
#                          makes one pass over the table, and applies both the
#                          7-day activity-window rollover and the xp_d0..xp_d6
#                          rotation to each row in one UPDATE per chunk via
#                          CASE expressions — a given row is only ever written
#                          once per night. record_activity() still rolls a
#                          single student's window forward lazily on their
#                          next activity, so this job isn't required for the
#                          binge-lock itself; it exists to decay `streak` back
#                          to 0 for students who go silent, to keep
#                          `is_bingeing` from going stale once a window
#                          closes, and to rotate the weekly XP store. See
#                          tap_lms.tapapp.jobs.nightly_window_maintenance for
#                          full rationale.
#   - run_tapapp_analytics_report: computes Tapapp Learner engagement
#                          metrics (DAL, archetype distribution, level
#                          distribution, submission gem totals, bingeing
#                          count) and writes them out via the Apps Script
#                          web app, same pattern as the CA analytics job.
#                          Named run_tapapp_analytics_report for the same
#                          Scheduled Job Type collision reason as above —
#                          the CA job owns "analytics_report.run_analytics_report".
#                          See tap_lms.tapapp.jobs.tapapp_analytics_report.
#
# Cron:
#   - */1 * * * *  — pe_dispatcher: per-PE event-driven dispatcher (task #15);
#                    processes overdue next_action_at, routes by next_action_type.
#                    Tightened from */2 to */1 min for the 100K-student MVP target
#                    (architecture §8.8 + ADR-003 audit log 2026-05-13). Combined
#                    with DISPATCH_BATCH_SIZE=1000 and 4 parallel workers gives
#                    240K actions/hour — drains a 100K week-boundary T19 burst in
#                    ~25 min. Hard prerequisite: partial index idx_pe_next_action
#                    (task #24, patch cr_004_scale.idx_pe_next_action) so the
#                    SELECT stays <50ms at scale.
#                  — flush_xp_queue: drains the Redis XP queue and batch-writes
#                    XP + level updates to tabCitizenship Learner. Runs every
#                    minute so XP is never more than 60s stale in the DB.
#   - 0 */2 * * *  — escalation_runner: 6-hour bulk escalation sweep (legacy
#                    batcher; will eventually be replaced by escalation_batcher
#                    in collection-mode rollout)
#   - 0 0 * * 1    — auto_advance_batch_week: weekly Monday sweep that bumps
#                    Batch.current_calendar_week and unblocks max_allowed_week
#                    on each PE
#   - 30 21 * * *  — run_xp_window_rotate (CA): nightly 03:00 IST job that
#                    flushes the CA Redis XP queue and rotates the 7-day XP
#                    window (xp_d0..xp_d6 -> weekly_xp) on tabCitizenship
#                    Learner. Both run_leaderboard_build and
#                    run_analytics_report below gate on this job's tracker
#                    (Citizenship Tasks "XP Window Rotate") having
#                    last_success_at == today before they'll proceed, so it
#                    must run in this same nightly window ahead of them.
#                  — run_leaderboard_build: nightly 03:00 IST leaderboard job.
#                    Rebuilds and uploads school/district/state/national JSON
#                    files to R2 once XP rotation has succeeded for the day.
#                  — run_analytics_report: nightly 03:00 IST analytics job.
#                    Computes 26 engagement/progress/retention/geography/
#                    cohort/achievement metrics and writes them to Google
#                    Sheets via the Apps Script web app. Waits for the XP
#                    rotate lock to clear (same-tick race with the job
#                    above), then requires xp_window_rotate's last_success_at
#                    to be today; if not, marks itself Failed with no partial
#                    writes and exits — no retry.
scheduler_events = {
    "daily": [
        "tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_incomplete_stages",
        "tap_lms.summer_program.scheduler.run_daily_actions",
        "tap_lms.summer_program.batch_activation.check_auto_activate",
        "tap_lms.tapapp.jobs.nightly_window_maintenance.run_nightly_window_maintenance",
        "tap_lms.tapapp.jobs.tapapp_analytics_report.run_tapapp_analytics_report",
    ],
    "cron": {
        "*/1 * * * *": [
            "tap_lms.summer_program.pe_dispatcher.process_program_actions",
            "tap_lms.ca.api.progress.learner.flush_xp_queue",
        ],
        # Retired 2026-05-21 (task #50): the legacy escalation_runner ran in
        # parallel with pe_dispatcher.handle_escalation (system A, post-CR-003)
        # without gating on canonical PE state. It double-escalated students
        # who already submitted and disagreed with the per-PE escalation
        # counter. The per-PE dispatcher fires escalations correctly when
        # next_action_at + next_action_type='escalation' are armed by T1
        # (content_no_response). escalation_runner.py is preserved as dead
        # code for one release cycle; remove the module after launch.
        # "0 */2 * * *": [
        #     "tap_lms.summer_program.escalation_runner.run_escalation_check",
        # ],
        "0 0 * * 1": [
            "tap_lms.summer_program.batch_admin.auto_advance_batch_week",
        ],
        # CR-005 (2026-05-15): Tuesday 03:30 UTC = Tuesday 09:00 IST.
        # Fires SP_Content_Delivery against each active BPR's `main`
        # Glific collection. Membership is maintained continuously by
        # state-machine transitions (Approach B) — this cron just fires.
        "30 3 * * 2": [
            "tap_lms.summer_program.scheduler.weekly_content_delivery_trigger",
        ],
        # Task #56 (2026-05-16): hourly watchdog for PEs stuck in
        # feedback_ready because Glific's F5 callback dropped silently.
        # LOG-only — does NOT auto-transition; operator replays manually.
        # See pre_launch.feedback_ready_watchdog for full rationale.
        # Task #17 (2026-05-28): two more hourly watchers added at the same
        # cadence. Both are read-only — they turn silent async failures
        # (Glific sync DLQ, RQ queue depth) into Error Log entries operators
        # can see in the Frappe Desk Error Log list view.
        "0 * * * *": [
            "tap_lms.summer_program.pre_launch.feedback_ready_watchdog",
            "tap_lms.summer_program.scheduler.glific_sync_dlq_watcher",
            "tap_lms.summer_program.scheduler.rq_queue_depth_watcher",
        ],
        # Task #97 / removed 2026-05-26 (L-027 MVP discipline):
        # `periodic_glific_reconcile` was wired here at */10 cadence as a
        # drift safety net. After diagnosing the real root cause of the
        # Himani / ST00051295 rendering bug (missing createContactsField
        # definitions, NOT value drift), the cron stopped being MVP-
        # justified — in production normal operation, students don't have
        # Desk access and code paths fire the sync hook correctly. The
        # `set_value` bypass is operator-driven (console backfills).
        #
        # The function `scheduler.periodic_glific_reconcile` is preserved
        # for MANUAL invocation from bench console when needed. Same for
        # `dev_tools.reconcile_pe_to_glific(pe_name)` and
        # `dev_tools.reconcile_batch_to_glific(batch_name)`.
        #
        # If post-launch logs show silent value drift, re-enable here at a
        # cadence appropriate to the observed frequency (likely daily, not
        # */10) — uncomment and `bench migrate`.
        # "*/10 * * * *": [
        #     "tap_lms.summer_program.scheduler.periodic_glific_reconcile",
        # ],
        "30 21 * * *": [
            "tap_lms.ca.jobs.xp_window_rotate.run_xp_window_rotate",
            "tap_lms.ca.jobs.leaderboard_build.run_leaderboard_build",
            "tap_lms.ca.jobs.analytics_report.run_analytics_report",
        ],
    },
}

# Page configurations
page_js = {"onboarding-flow-trigger": "public/js/onboarding_flow_trigger.js"}

# Reports
report_script_custom_doctypes = ["StudentStageProgress"]


# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/tap_lms/css/tap_lms.css"
# app_include_js = "/assets/tap_lms/js/tap_lms.js"

# include js, css files in header of web template
# web_include_css = "/assets/tap_lms/css/tap_lms.css"
# web_include_js = "/assets/tap_lms/js/tap_lms.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "tap_lms/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#       "Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
#       "methods": "tap_lms.utils.jinja_methods",
#       "filters": "tap_lms.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "tap_lms.install.before_install"
# after_install = "tap_lms.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "tap_lms.uninstall.before_uninstall"
# after_uninstall = "tap_lms.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "tap_lms.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
#       "Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#       "Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
#       "ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
#       "*": {
#               "on_update": "method",
#               "on_cancel": "method",
#               "on_trash": "method"
#       }
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
#       "all": [
#               "tap_lms.tasks.all"
#       ],
#       "daily": [
#               "tap_lms.tasks.daily"
#       ],
#       "hourly": [
#               "tap_lms.tasks.hourly"
#       ],
#       "weekly": [
#               "tap_lms.tasks.weekly"
#       ],
#       "monthly": [
#               "tap_lms.tasks.monthly"
#       ],
# }

# Testing
# -------

# before_tests = "tap_lms.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
#       "frappe.desk.doctype.event.event.get_events": "tap_lms.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
#       "Task": "tap_lms.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]


# User Data Protection
# --------------------

# user_data_fields = [
#       {
#               "doctype": "{doctype_1}",
#               "filter_by": "{filter_by}",
#               "redact_fields": ["{field_1}", "{field_2}"],
#               "partial": 1,
#       },
#       {
#               "doctype": "{doctype_2}",
#               "filter_by": "{filter_by}",
#               "partial": 1,
#       },
#       {
#               "doctype": "{doctype_3}",
#               "strict": False,
#       },
#       {
#               "doctype": "{doctype_4}"
#       }
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#       "tap_lms.auth.validate"
# ]

fixtures = [{ "doctype": "Client Script", "filters": [ ["module", "in", ( "Tap Lms" )] ] }]