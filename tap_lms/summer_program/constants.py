"""
Summer Program Constants
tap_lms/summer_program/constants.py

Enums and shared constants for the Summer Program module.
All values match the ProgramEnrollment doctype Select options exactly.
"""


# ── Archetypes ──────────────────────────────────────────────
ARCHETYPE_DORMANT = "Dormant"
ARCHETYPE_FENCE_SITTER = "Fence Sitter"
ARCHETYPE_IRREGULAR_SUBMITTER = "Irregular Submitter"
ARCHETYPE_SUBMITTER = "Submitter"

ALL_ARCHETYPES = [
    ARCHETYPE_DORMANT,
    ARCHETYPE_FENCE_SITTER,
    ARCHETYPE_IRREGULAR_SUBMITTER,
    ARCHETYPE_SUBMITTER,
]

# ── Experiment Arms ─────────────────────────────────────────
ARM_DEFAULT = "default"
ARM_A = "arm_a"
ARM_B = "arm_b"

ALL_ARMS = [ARM_DEFAULT, ARM_A, ARM_B]

# ── Collection labels ───────────────────────────────────────
ARCHETYPE_KEY_MAP = {
    ARCHETYPE_DORMANT: "dormant",
    ARCHETYPE_FENCE_SITTER: "fence_sitter",
    ARCHETYPE_IRREGULAR_SUBMITTER: "irregular_submitter",
    ARCHETYPE_SUBMITTER: "submitter",
}


def collection_label(batch_id, archetype, arm):
    """Build the Glific collection label for an archetype×arm combo."""
    arch_key = ARCHETYPE_KEY_MAP.get(archetype, archetype.lower().replace(" ", "_"))
    return f"SP_{batch_id}_{arch_key}_{arm}"


# ── Resolved Flow States (matches PE doctype Select) ───────
# These are the 12 valid states for ProgramEnrollment.resolved_flow_state
STATE_NORMAL_CONTENT = "normal_content_delivery"
STATE_NORMAL_ESCALATION = "normal_escalation"
STATE_REMEDIAL_CONTENT = "remedial_content_delivery"
STATE_REMEDIAL_ESCALATION = "remedial_escalation"
STATE_GRACE_WAITING = "grace_waiting"
STATE_PAUSED_NO_ACTIVITY = "paused_no_activity"
STATE_PAUSED_BINGE = "paused_binge"
STATE_SUBMITTED_AWAITING = "submitted_awaiting_feedback"
STATE_FEEDBACK_READY = "feedback_ready"
STATE_WEEK_COMPLETED = "week_completed"
STATE_PROGRAM_COMPLETED = "program_completed"
STATE_PROGRAM_DROPPED = "program_dropped"

# Content delivery states (Core or Remedial)
CONTENT_DELIVERY_STATES = [STATE_NORMAL_CONTENT, STATE_REMEDIAL_CONTENT]

# Escalation states
ESCALATION_STATES = [STATE_NORMAL_ESCALATION, STATE_REMEDIAL_ESCALATION]

# Paused states
PAUSED_STATES = [STATE_PAUSED_NO_ACTIVITY, STATE_PAUSED_BINGE]

# Terminal states (no further scheduling)
TERMINAL_STATES = [STATE_PROGRAM_COMPLETED, STATE_PROGRAM_DROPPED]


# ── Journey Labels (matches PE doctype Select) ─────────────
LABEL_ENROLLED = "enrolled"
LABEL_CONTENT_DELIVERED = "content_delivered"
LABEL_SUBMITTED = "submitted"
LABEL_FEEDBACK_DELIVERED = "feedback_delivered"
LABEL_WEEK_SUMMARY_SENT = "week_summary_sent"
LABEL_GRACE_WINDOW = "grace_window"
LABEL_PAUSED = "paused"
LABEL_RESUMED = "resumed"
LABEL_COMPLETED = "completed"
LABEL_DROPPED = "dropped"
LABEL_WEEK_ADVANCED = "week_advanced"


# ── Program Status (matches PE doctype Select) ─────────────
PROGRAM_ACTIVE = "active"
PROGRAM_PAUSED = "paused"
PROGRAM_COMPLETED = "completed"
PROGRAM_DROPPED = "dropped"


# ── Paths ──────────────────────────────────────────────────
PATH_CORE = "Core"
PATH_REMEDIAL = "Remedial"


# ── Scheduler Action Types (matches PE doctype Select) ─────
ACTION_CONTENT_DELIVERY = "content_delivery"
ACTION_ESCALATION = "escalation"
ACTION_WEEK_ADVANCEMENT = "week_advancement"
ACTION_FEEDBACK_NOTIFICATION = "feedback_notification"
ACTION_RE_ENGAGEMENT = "re_engagement"
ACTION_GRACE_CHECK = "grace_check"
ACTION_PAUSE_CHECK = "pause_check"
ACTION_FEEDBACK_TIMEOUT = "feedback_timeout"
ACTION_GRACE_REMINDER = "grace_reminder"

ALL_ACTION_TYPES = [
    ACTION_CONTENT_DELIVERY,
    ACTION_ESCALATION,
    ACTION_WEEK_ADVANCEMENT,
    ACTION_FEEDBACK_NOTIFICATION,
    ACTION_RE_ENGAGEMENT,
    ACTION_GRACE_CHECK,
    ACTION_PAUSE_CHECK,
    ACTION_FEEDBACK_TIMEOUT,
    ACTION_GRACE_REMINDER,
]

# Collection-based actions (one API call per collection)
ACTION_REENGAGEMENT = "re_engagement"

COLLECTION_ACTIONS = [
    ACTION_CONTENT_DELIVERY,
    ACTION_ESCALATION,
    ACTION_REENGAGEMENT,
]

PER_STUDENT_ACTIONS = [
    ACTION_WEEK_ADVANCEMENT,
    ACTION_GRACE_CHECK,
    ACTION_GRACE_REMINDER,
    ACTION_PAUSE_CHECK,
    ACTION_FEEDBACK_TIMEOUT,
    ACTION_RE_ENGAGEMENT,
]

# Maps action type → BatchProgramRun field that stores the Glific flow ID
ACTION_FLOW_FIELD_MAP = {
    ACTION_CONTENT_DELIVERY: "content_delivery_flow",
    ACTION_ESCALATION: "escalation_flow",
    ACTION_RE_ENGAGEMENT: "reengagement_flow",
    ACTION_GRACE_REMINDER: "grace_notification_flow",
    ACTION_GRACE_CHECK: "grace_notification_flow",
    ACTION_PAUSE_CHECK: "binge_info_flow",
    "program_complete": "program_complete_flow",
    # NOTE: feedback_delivery_flow removed — FeedbackConsumer handles
    # feedback notification via its own Glific Flow lookup (label="feedback")
}


# ── Pause Reasons ──────────────────────────────────────────
PAUSE_NO_ACTIVITY = "no_activity"
PAUSE_BINGE_LIMIT = "binge_limit"


# ── BatchProgramRun statuses ──────────────────────────────
BPR_DRAFT = "draft"
BPR_IMPORTING = "importing"
BPR_ENROLLING = "enrolling"
BPR_COLLECTIONS_READY = "collections_ready"
BPR_ACTIVE = "active"
BPR_COMPLETED = "completed"

BPR_STATUS_FLOW = [
    BPR_DRAFT, BPR_IMPORTING, BPR_ENROLLING,
    BPR_COLLECTIONS_READY, BPR_ACTIVE, BPR_COMPLETED,
]

# ── Validation statuses ──────────────────────────────────
VALIDATION_NOT_RUN = "not_run"
VALIDATION_PASSED = "passed"
VALIDATION_FAILED = "failed"


# ── Glific Contact Field Keys ─────────────────────────────
# These are the 18 contact field names set on Glific contacts
CF_STUDENT_ID = "student_id"
CF_BATCH_ID = "batch_id"
CF_ARCHETYPE = "archetype"
CF_LANGUAGE = "language"
CF_RESOLVED_FLOW_STATE = "resolved_flow_state"
CF_CURRENT_WEEK = "current_week"
CF_CURRENT_PATH = "current_path"
CF_CURRENT_TIER = "current_tier"
CF_PROGRAM_STATUS = "program_status"
CF_TOTAL_POINTS = "total_points"
CF_CURRENT_STREAK = "current_streak"
CF_GRACE_WINDOW_END = "grace_window_end_at"
CF_EXPECTED_SUBMISSION = "current_expected_submission_type"
CF_EXPERIMENT_ARM = "experiment_arm"
CF_COURSE_LEVEL = "course_level"
CF_STUDENT_NAME = "student_name"
CF_LAST_ESCALATION_STEP = "last_escalation_step"
CF_SUBMISSION_COUNT = "submission_count"


# ── Tier mapping ──────────────────────────────────────────
TIER_BY_WEEK = {1: "Basic", 2: "Intermediate"}
DEFAULT_TIER = "Advanced"
REMEDIAL_TIER = "Remedial"


# ── Scheduler constants ──────────────────────────────────
ENROLLMENT_QUEUE = "long"
COLLECTION_BATCH_SIZE = 500
ENROLLMENT_CHUNK_SIZE = 100

# Grace window
GRACE_WINDOW_DAYS = 14
GRACE_REMINDER_DAYS = [7, 11, 13]  # days after grace start

# Re-engagement
MAX_REENGAGEMENT_ATTEMPTS = 3
REENGAGEMENT_DAYS = [3, 7, 14]  # days after pause

# Feedback
FEEDBACK_TIMEOUT_HOURS = 4
MAX_FEEDBACK_RETRIES = 3

# Delivery
MAX_DELIVERY_FAILURES = 3
