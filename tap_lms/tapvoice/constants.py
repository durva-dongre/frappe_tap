RUN_DOCTYPE = "Tap Voice Run"
SETTINGS_DOCTYPE = "Tap Voice Settings"

STATUS_DRAFT = "Draft"
STATUS_DEPLOYING = "Deploying"
STATUS_STARTING = "Starting"
STATUS_RUNNING = "Running"
STATUS_STOPPING = "Stopping"
STATUS_COMPLETED = "Completed"
STATUS_COMPLETED_WITH_FAILURES = "Completed With Failures"
STATUS_STOPPED = "Stopped"
STATUS_FAILED = "Failed"
STATUS_TIMED_OUT = "Timed Out"
STATUS_LOST = "Lost"
STATUS_DEPLOY_FAILED = "Deploy Failed"
STATUS_SKIPPED = "Skipped"

ACTIVE_STATUSES = frozenset(
    {STATUS_DEPLOYING, STATUS_STARTING, STATUS_RUNNING, STATUS_STOPPING}
)
TERMINAL_STATUSES = frozenset(
    {
        STATUS_COMPLETED,
        STATUS_COMPLETED_WITH_FAILURES,
        STATUS_STOPPED,
        STATUS_FAILED,
        STATUS_TIMED_OUT,
        STATUS_LOST,
        STATUS_DEPLOY_FAILED,
        STATUS_SKIPPED,
    }
)

BAD_RUN_STATUSES = frozenset(
    {STATUS_FAILED, STATUS_TIMED_OUT, STATUS_LOST, STATUS_DEPLOY_FAILED}
)

TERMINATION_NOT_NEEDED = "Not Needed"
TERMINATION_PENDING = "Pending"
TERMINATION_VERIFIED = "Verified"
TERMINATION_MANUAL_ACTION_NEEDED = "Manual Action Needed"

TRIGGER_MANUAL = "Manual"
TRIGGER_CRON = "Cron"

DECISION_DEPLOY = "Deploy"
DECISION_SKIP_NOTHING = "Skip: nothing to convert"
DECISION_SKIP_BELOW_MINIMUM = "Skip: below minimum"
DECISION_SKIP_BUDGET = "Skip: budget"
DECISION_SKIP_DISABLED = "Skip: disabled"
DECISION_SKIP_BLOCKED = "Skip: blocked"

PERMANENT_FAILURE_REASONS = frozenset(
    {
        "silent",
        "too_short",
        "too_long",
        "pace_short",
        "pace_long",
        "too_few_tokens",
        "bad_codes",
        "truncated",
        "prompt_too_long",
        "empty",
        "non_finite",
        "text_too_long",
        "empty_text",
    }
)

SECRET_RUNPOD_API_KEY = "runpod_api_key"
SECRET_RUNPOD_POD_API_KEY = "runpod_pod_api_key"
SECRET_TTS_POD_SHARED_SECRET = "tts_pod_shared_secret"
SECRET_TTS_GCS_SERVICE_ACCOUNT_JSON_B64 = "tts_gcs_service_account_json_b64"

REQUIRED_SECRET_KEYS = (
    SECRET_RUNPOD_API_KEY,
    SECRET_TTS_POD_SHARED_SECRET,
    SECRET_TTS_GCS_SERVICE_ACCOUNT_JSON_B64,
)

FORMAT_OGG = "ogg"

OUTCOME_WRITTEN = "written"
OUTCOME_ALREADY_SET = "already_set"
OUTCOME_STALE = "stale"
OUTCOME_HASH_MISMATCH = "hash_mismatch"
OUTCOME_BAD_URL = "bad_url"
OUTCOME_NOT_IN_MANIFEST = "not_in_manifest"
OUTCOME_CHANGED_DURING_WRITE = "changed_during_write"
OUTCOME_SUBMISSION_FAILED = "submission_failed"
OUTCOME_RECORDED_FAILURE = "recorded_failure"

POD_REASON_COMPLETED = "completed"
POD_REASON_COMPLETED_WITH_FAILURES = "completed_with_failures"
POD_REASON_EMPTY = "empty"
POD_REASON_STOPPED = "stopped"
POD_REASON_TIMEOUT = "timeout"
POD_REASON_STARTUP_TIMEOUT = "startup_timeout"
POD_REASON_EXCEPTION = "exception"
POD_BREAKER_PREFIX = "breaker_"

PROGRESS_MAX_RECORDS = 500
FAILED_ITEMS_MAX_ENTRIES = 2000
FAILURE_REASONS_MAX_ENTRIES = 100
BODY_SIZE_CAP_BYTES = 2 * 1024 * 1024
LOG_CAP_BYTES = 200 * 1024
MAX_URL_LENGTH = 140

HEAD_CHECK_TIMEOUT_SECONDS = 5
HEAD_CHECK_MAX_WORKERS = 8
HEAD_CHECK_BATCH_BUDGET_SECONDS = 15