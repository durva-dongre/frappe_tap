"""
Vocallabs parent-call integration — CR-003.

tap_lms/summer_program/vocallabs.py

Per-call flow (Postman reference: createAuthToken → createContactGroup [unused
in steady state, contact group is configured once] → addMultipleContactsToGroup →
initiateVocallabsCall):

1. Get cached auth token, or fetch + cache for VoiceAgentSettings.auth_token_cache_ttl
2. Add parent contact to default group with the rendered status template
3. Initiate call with agent_id + returned prospect_id

Retry: 5 attempts via the P-007 retry/DLQ pattern shared with Glific sync
(state_machine._sync_contact_fields_job) and the feedback pipeline
(save_submission.enqueue_submission). DLQ to Frappe Error Log titled
"SP Vocallabs DLQ — manual replay required" with a structured payload
{student_id, pe_name, week, escalation_order, parent_phone, error}.

NEVER bubble exceptions; always log to Error Log and return False on failure
so the dispatcher continues toward drop (CR-003 §Edge case E4: "Vocallabs DLQ
during grace tail: just log and continue toward drop").

Phone resolution:
    Per CR-003 §"Phone resolution" the parent's phone is `Student.phone`
    (the student uses the parent's device). No `Student.parent_phone`
    field is added in this CR; a future CR can split this if Student
    ever gets its own phone.
"""
import json

import frappe
from frappe.utils import now_datetime

from tap_lms.summer_program.constants import (
    VOCALLABS_MAX_RETRIES,
    VOCALLABS_RETRY_LOG_TITLE,
    VOCALLABS_DLQ_LOG_TITLE,
    VOCALLABS_HTTP_TIMEOUT_SECONDS,
    VOCALLABS_TOKEN_CACHE_KEY,
    VOCALLABS_DEFAULT_TOKEN_TTL,
)


# ════════════════════════════════════════════════════════════
# Public entry point
# ════════════════════════════════════════════════════════════


def initiate_parent_call(pe_name, escalation_step, retry_count=0):
    """Initiate a Vocallabs parent call for a PE's current escalation step.

    Frappe-enqueueable from `handle_escalation` when
    `escalation_step['escalation_type'] == 'parent_call'`.

    Args:
        pe_name: ProgramEnrollment document name.
        escalation_step: dict from _get_escalation_steps_for_pe; carries
            `escalation_order`, `escalation_type`, `hours_after_previous`,
            `points_awarded`.
        retry_count: internal — incremented on retry.

    Returns:
        True on successful Vocallabs hand-off, False on any failure
        (including all retries exhausted). False is also returned for
        config-level skips (Vocallabs disabled, no ParentCallConfig
        resolved). The dispatcher does NOT block on this — the grace
        clock keeps ticking and the PE proceeds toward drop on the
        normal schedule.
    """
    try:
        pe = frappe.get_doc("ProgramEnrollment", pe_name)
    except frappe.DoesNotExistError:
        frappe.log_error(
            f"Vocallabs: PE {pe_name} not found; skipping parent call.",
            VOCALLABS_DLQ_LOG_TITLE,
        )
        return False

    # ── Settings check ──────────────────────────────────────
    settings = _get_voice_agent_settings()
    if not settings:
        frappe.log_error(
            f"Vocallabs: VoiceAgentSettings singleton missing for PE {pe_name}; skipping.",
            "SP Vocallabs Config",
        )
        return False

    if not getattr(settings, "enabled", 0):
        # Feature flag off — log + skip; this is NOT an error and NOT retried.
        frappe.log_error(
            f"Vocallabs disabled (VoiceAgentSettings.enabled=0); "
            f"skipping parent call for PE {pe_name}.",
            "SP Vocallabs Skipped",
        )
        return False

    if not settings.agent_id:
        frappe.log_error(
            f"Vocallabs: VoiceAgentSettings.agent_id is unset; "
            f"cannot initiate call for PE {pe_name}.",
            "SP Vocallabs Config",
        )
        return False

    # ── Resolve config ──────────────────────────────────────
    config = _resolve_parent_call_config(pe, pe.current_week or 1, settings)
    if not config:
        # Per CR-003 §E3: skip + warn. Config issue, not a runtime failure.
        frappe.log_error(
            f"Vocallabs: no ParentCallConfig resolved for PE {pe_name} "
            f"(week={pe.current_week}); neither per-LU content nor "
            f"VoiceAgentSettings.default_parent_call_config is set. "
            f"Skipping parent call; the cohort is NOT blocked.",
            "SP Vocallabs Config",
        )
        return False

    # ── Resolve student + parent phone ──────────────────────
    student = frappe.get_doc("Student", pe.student)
    parent_phone = (getattr(student, "phone", "") or "").strip()
    if not parent_phone:
        frappe.log_error(
            f"Vocallabs: Student {pe.student} has no phone; "
            f"cannot place parent call for PE {pe_name}.",
            "SP Vocallabs Config",
        )
        return False

    # ── Render status ──────────────────────────────────────
    status_text = _render_status_template(
        config.status_template or "",
        pe, student, escalation_step,
    )

    # ── Run the 3-step Vocallabs sequence ──────────────────
    try:
        token = _get_auth_token(settings)
        if not token:
            raise RuntimeError("Vocallabs auth token fetch returned empty token")

        call_response = _call_vocallabs(
            settings=settings,
            token=token,
            parent_phone=parent_phone,
            student_name=_student_display(student),
            status_text=status_text,
        )
        if not call_response:
            raise RuntimeError("Vocallabs call sequence returned no response")
    except Exception as e:
        return _handle_failure(
            pe=pe, escalation_step=escalation_step,
            parent_phone=parent_phone, error=e, retry_count=retry_count,
        )

    # Success — log a successful parent-call attempt for the funnel.
    # Field names per programeventlog.json: `enrollment` (reqd), `student`
    # (reqd), `batch` (reqd), `program_type`, `week`, `event_type`,
    # `trigger_source`, `details`. Earlier draft used `program_enrollment`
    # which silently failed Frappe validation — see code review B2.
    try:
        frappe.get_doc({
            "doctype": "ProgramEventLog",
            "enrollment": pe.name,
            "student": pe.student,
            "batch": pe.batch,
            "program_type": pe.program_type or "Summer",
            "week": pe.current_week,
            "event_type": "escalation_sent",
            "trigger_source": "scheduler",
            "created_at": now_datetime(),
            "details": json.dumps({
                "channel": "parent_call",
                "escalation_order": escalation_step.get("escalation_order"),
                "vocallabs_response": _safe_summary(call_response),
            }),
        }).insert(ignore_permissions=True)
    except frappe.ValidationError as log_err:
        # Narrow exception per L-007. Logging failure shouldn't kill the
        # success path; surface to Error Log so ops can backfill the funnel.
        frappe.log_error(
            f"Vocallabs: succeeded but event_log insert failed for PE {pe_name}: {log_err}",
            "SP Vocallabs Log",
        )

    return True


# ════════════════════════════════════════════════════════════
# Settings + auth token cache
# ════════════════════════════════════════════════════════════


def _get_voice_agent_settings():
    """Read the VoiceAgentSettings singleton once per invocation.

    Returns the doc or None if the singleton is missing.
    """
    try:
        return frappe.get_single("VoiceAgentSettings")
    except Exception as e:
        frappe.log_error(
            f"Vocallabs: failed to load VoiceAgentSettings: {e}",
            "SP Vocallabs Config",
        )
        return None


def _get_auth_token(settings):
    """Return a cached or freshly-minted Vocallabs auth token.

    Cache: `frappe.cache().get_value(VOCALLABS_TOKEN_CACHE_KEY)`, TTL =
    `settings.auth_token_cache_ttl` (default `VOCALLABS_DEFAULT_TOKEN_TTL`
    = 3600s if unset). The cache is keyed without per-tenant scoping
    because we have one Vocallabs account per Frappe site.

    Edge case E5 (cache stampede): with concurrent workers all seeing a
    missing token, multiple createAuthToken calls may fire. Vocallabs
    returns the same token regardless; the last-writer-wins for the
    cache key is fine. A single-flight lock is filed as a follow-up.
    """
    cached = frappe.cache().get_value(VOCALLABS_TOKEN_CACHE_KEY)
    if cached:
        return cached

    # Cache miss — fetch fresh token.
    service_url = (settings.service_url or "").rstrip("/")
    if not service_url:
        raise RuntimeError("Vocallabs: VoiceAgentSettings.service_url is unset")
    if not settings.client_id:
        raise RuntimeError("Vocallabs: VoiceAgentSettings.client_id is unset")

    # client_secret is a Password field; read via get_password so the
    # decrypted value is returned (not the encrypted blob).
    try:
        client_secret = settings.get_password("client_secret", raise_exception=False)
    except Exception:
        client_secret = None
    if not client_secret:
        raise RuntimeError("Vocallabs: VoiceAgentSettings.client_secret is unset")

    # Vocallabs auth contract (verified via Postman 2026-05-21):
    # POST {service_url}/b2b/createAuthToken/   <- note trailing slash
    # Body uses camelCase clientId/clientSecret (NOT snake_case).
    response = _http_post(
        url=f"{service_url}/b2b/createAuthToken/",
        payload={
            "clientId": settings.client_id,
            "clientSecret": client_secret,
        },
        headers={"Content-Type": "application/json"},
    )

    token = _extract_auth_token(response)
    if not token:
        raise RuntimeError(
            f"Vocallabs: createAuthToken returned no authToken; response={_safe_summary(response)}"
        )

    ttl = int(getattr(settings, "auth_token_cache_ttl", None) or VOCALLABS_DEFAULT_TOKEN_TTL)
    frappe.cache().set_value(VOCALLABS_TOKEN_CACHE_KEY, token, expires_in_sec=ttl)
    return token


def _extract_auth_token(response):
    """Vocallabs' createAuthToken response has shape `{authToken: "..."}`;
    defensive-extract so we don't crash on response-shape drift.

    Some Vocallabs endpoints wrap the response in `[{...}]` (observed for
    createContactGroup); unwrap defensively in case auth eventually adopts
    the same pattern.
    """
    if isinstance(response, list):
        response = response[0] if response else {}
    if not isinstance(response, dict):
        return None
    return (
        response.get("authToken")
        or response.get("auth_token")
        or response.get("token")
    )


# ════════════════════════════════════════════════════════════
# Config resolution
# ════════════════════════════════════════════════════════════


def _resolve_parent_call_config(pe, current_week, settings):
    """Resolve the ParentCallConfig for the current week.

    Resolution chain per CR-003 §E3:
      1. Look up the week's LearningUnit; scan its UnitContentItem rows for
         one with `content_type == "ParentCallConfig"`. If found, return
         that ParentCallConfig doc.
      2. Fall back to `VoiceAgentSettings.default_parent_call_config`.
      3. Return None — caller logs a warning and skips the step.

    `_get_learning_unit` is the canonical helper in student_progression_sp.
    """
    from tap_lms.summer_program.student_progression_sp import _get_learning_unit

    tier = getattr(pe, "current_tier", None) or "Basic"
    if pe.course_level:
        try:
            learning_unit = _get_learning_unit(pe.course_level, current_week, tier)
        except Exception:
            learning_unit = None
        if learning_unit:
            item = frappe.db.get_value(
                "UnitContentItem",
                {
                    "parent": learning_unit,
                    "parenttype": "LearningUnit",
                    "content_type": "ParentCallConfig",
                },
                "content",
            )
            if item:
                try:
                    config = frappe.get_doc("ParentCallConfig", item)
                    # CR-003 §M4: `is_active` is the soft-disable flag. A
                    # disabled config means "don't fire this step"; fall
                    # through to the default. If the default is also
                    # inactive, the caller skips the step.
                    if getattr(config, "is_active", 1):
                        return config
                except frappe.DoesNotExistError:
                    # LU referenced a now-deleted config — fall through.
                    pass

    # Fallback to the singleton's default.
    default_name = getattr(settings, "default_parent_call_config", None)
    if default_name:
        try:
            default_config = frappe.get_doc("ParentCallConfig", default_name)
            if getattr(default_config, "is_active", 1):
                return default_config
        except frappe.DoesNotExistError:
            return None

    return None


# ════════════════════════════════════════════════════════════
# Template rendering
# ════════════════════════════════════════════════════════════


_TEMPLATE_VARS = (
    "student_name",
    "week",
    "archetype",
    "course_level",
    "path",
    "escalation_order",
    "escalation_type",
    "language",
)


def _render_status_template(template, pe, student, step):
    """Render the status_template with the documented variables.

    Supported variables (per CR-003 §"Parent-call integration"):
        {student_name}, {week}, {archetype}, {course_level}, {path},
        {escalation_order}, {escalation_type}, {language}

    Uses `str.format(**ctx)` so a missing variable in the template is fine
    (only the variables referenced are required). If the template
    references an UNDOCUMENTED variable, KeyError fires and we log to
    Error Log then return the raw template — the call still places (the
    operator can see the literal `{foo}` and fix the template).

    Note: `language` is the student's preferred language (Student.language).
    Useful for templates that branch wording, but the SPOKEN language of
    the call is determined by the Vocallabs Agent itself (the agent's
    `language` + `voice_id` config). To support multiple spoken languages
    you need one Vocallabs agent per language and a per-language agent_id
    lookup at call time — see task #48.
    """
    if not template:
        return ""

    ctx = {
        "student_name": _student_display(student),
        "week": str(pe.current_week or 0),
        "archetype": pe.archetype or "",
        "course_level": pe.course_level or "",
        "path": pe.current_path or "",
        "escalation_order": str(step.get("escalation_order", "") or ""),
        "escalation_type": step.get("escalation_type", "") or "",
        "language": getattr(student, "language", "") or "",
    }

    try:
        return template.format(**ctx)
    except KeyError as e:
        frappe.log_error(
            f"Vocallabs: status_template references undocumented variable "
            f"{e}; PE={pe.name}. Supported vars: {_TEMPLATE_VARS}. "
            f"Returning raw template.",
            "SP Vocallabs Template",
        )
        return template
    except Exception as e:
        frappe.log_error(
            f"Vocallabs: status_template render failed: {e}; PE={pe.name}.",
            "SP Vocallabs Template",
        )
        return template


def _student_display(student):
    """Per L-???: Student.name1 is the canonical display name field."""
    from tap_lms.summer_program.utils import get_student_display_name
    return get_student_display_name(student)


# ════════════════════════════════════════════════════════════
# HTTP — Vocallabs API
# ════════════════════════════════════════════════════════════


def _call_vocallabs(settings, token, parent_phone, student_name, status_text):
    """Run steps 2 + 3 of the Vocallabs sequence.

    Verified API contract (Postman 2026-05-21):

    Step 2 — POST {service_url}/b2b/vocallabs/addMultipleContactsToGroup
      Body: {
        "prospects": [
          {
            "name": <parent display name>,
            "phone": <E.164 phone>,
            "data": {
              "contact": <parent display name>,
              "student_name": <student name>,
              "status": <rendered status template>
            },
            "prospect_group_id": <default_contact_group_id>,
            "client_id": <VoiceAgentSettings.client_id>
          }
        ]
      }
      Response (verified): {
        "data": {
          "insert_vocallabs_prospects": {
            "affected_rows": 1,
            "returning": [{"id": "<uuid>", ...}]
          }
        }
      }

    Step 3 — POST {service_url}/b2b/vocallabs/initiateVocallabsCall
      Body: {"agentId": <agent_id>, "prospect_id": <uuid from step 2>}
      Note `prospect_id` is snake_case (not camelCase like `agentId`).

    Returns the final call response dict on success, None on failure
    (caller treats this as a runtime error and retries via P-007).
    """
    service_url = (settings.service_url or "").rstrip("/")
    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Vocallabs requires every prospect to have a `name`. We don't have the
    # parent's actual name stored (CR-003 just uses Student.phone), so use
    # the MVP placeholder "Parent of <student>" — it's what the agent's
    # template variable {{ contact }} will resolve to during the call.
    # A future CR can add Student.parent_name and replace this.
    parent_display = f"Parent of {student_name}" if student_name else "Parent"

    # ── Step 2: add parent contact to default group ─────────
    add_payload = {
        "prospects": [
            {
                "name": parent_display,
                "phone": parent_phone,
                # `data` is the per-contact variables block consumed by the
                # Vocallabs agent's prompt template at call time. Keys must
                # match what the agent prompt references — `contact`,
                # `student_name`, `status` per the Postman reference.
                "data": {
                    "contact": parent_display,
                    "student_name": student_name,
                    "status": status_text,
                },
                "prospect_group_id": settings.default_contact_group_id or "",
                "client_id": settings.client_id or "",
            },
        ],
    }
    add_response = _http_post(
        url=f"{service_url}/b2b/vocallabs/addMultipleContactsToGroup",
        payload=add_payload,
        headers=auth_headers,
    )
    prospect_id = _extract_prospect_id(add_response)
    if not prospect_id:
        raise RuntimeError(
            f"Vocallabs: addMultipleContactsToGroup returned no prospect_id; "
            f"response={_safe_summary(add_response)}"
        )

    # ── Step 3: initiate the call ───────────────────────────
    # Note: `agentId` is camelCase but `prospect_id` is snake_case per the
    # verified Postman contract. Inconsistent on Vocallabs' side; don't fix
    # this to be consistent — match the API.
    call_payload = {
        "agentId": settings.agent_id,
        "prospect_id": prospect_id,
    }
    call_response = _http_post(
        url=f"{service_url}/b2b/vocallabs/initiateVocallabsCall",
        payload=call_payload,
        headers=auth_headers,
    )
    return call_response


def _extract_prospect_id(response):
    """Extract the prospect UUID from Vocallabs' addMultipleContactsToGroup
    response.

    Verified shape (Postman 2026-05-21):
      {"data": {"insert_vocallabs_prospects": {"affected_rows": 1,
                                               "returning": [{"id": "<uuid>", ...}]}}}

    Some Vocallabs endpoints (e.g., createContactGroup) wrap the response
    in a single-element list `[{...}]` instead of returning the object
    directly — unwrap defensively so we work with either shape.
    """
    if isinstance(response, list):
        response = response[0] if response else {}
    if not isinstance(response, dict):
        return None

    # Primary: the documented nested shape.
    data = response.get("data") or {}
    ins = data.get("insert_vocallabs_prospects") or {}
    returning = ins.get("returning") or []
    if returning and isinstance(returning, list):
        first = returning[0] or {}
        if first.get("id"):
            return first["id"]

    # Defensive fallbacks for shape drift.
    return (
        response.get("prospect_id")
        or response.get("prospectId")
        or response.get("id")
        or data.get("prospect_id")
        or data.get("id")
    )


def _http_post(url, payload, headers):
    """POST with a 10s timeout. Tries `frappe.integrations.utils.make_post_request`
    first (so request audit + retry-policy plumbing applies); falls back to
    `requests.post` if the helper is unavailable.

    Returns the parsed JSON response (dict) or raises.
    """
    # Try Frappe's helper first — it centralizes outbound HTTP audit.
    try:
        from frappe.integrations.utils import make_post_request
        return make_post_request(
            url,
            data=json.dumps(payload),
            headers=headers,
        )
    except ImportError:
        pass
    except Exception as e:
        # Frappe's helper raised something; bubble it so the caller can retry.
        raise RuntimeError(f"Vocallabs HTTP error (Frappe helper): {e}")

    # Fallback to raw requests.
    try:
        import requests
    except ImportError:
        raise RuntimeError(
            "Vocallabs: requests library not available and "
            "frappe.integrations.utils.make_post_request not importable."
        )

    response = requests.post(
        url, data=json.dumps(payload),
        headers=headers, timeout=VOCALLABS_HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        raise RuntimeError(
            f"Vocallabs: non-JSON response body from {url}: {response.text[:500]!r}"
        )


# ════════════════════════════════════════════════════════════
# Retry + DLQ (P-007 / L-015)
# ════════════════════════════════════════════════════════════


def _handle_failure(pe, escalation_step, parent_phone, error, retry_count):
    """Mirror of state_machine._sync_contact_fields_job's retry policy:
    5 retries on transient failures, then DLQ to Error Log with a payload
    the operator can replay manually.

    Per CR-003 §E4 a Vocallabs DLQ does NOT extend the grace window. The
    PE proceeds toward drop on its normal schedule.
    """
    retry_count = (retry_count or 0) + 1
    pe_name = pe.name
    escalation_order = escalation_step.get("escalation_order")
    week = pe.current_week

    if retry_count <= VOCALLABS_MAX_RETRIES:
        # Log the transient + re-enqueue (no backoff for parity with the
        # Glific sync retry policy in state_machine.py).
        frappe.log_error(
            title=VOCALLABS_RETRY_LOG_TITLE,
            message=(
                f"Vocallabs transient failure "
                f"(attempt {retry_count}/{VOCALLABS_MAX_RETRIES + 1}) "
                f"for PE {pe_name} (student={pe.student}, "
                f"week={week}, escalation_order={escalation_order}, "
                f"parent_phone={parent_phone}): {error}"
            ),
        )
        try:
            frappe.enqueue(
                "tap_lms.summer_program.vocallabs.initiate_parent_call",
                queue="long",
                timeout=300,
                pe_name=pe_name,
                escalation_step=escalation_step,
                retry_count=retry_count,
            )
            return False
        except Exception as enqueue_err:
            # Double-fault — surface to DLQ immediately so the call request
            # isn't silently lost (mirrors state_machine.py's double-fault).
            frappe.log_error(
                title=VOCALLABS_DLQ_LOG_TITLE,
                message=json.dumps({
                    "reason": "double_fault_enqueue_failed",
                    "student_id": pe.student,
                    "pe_name": pe_name,
                    "week": week,
                    "escalation_order": escalation_order,
                    "parent_phone": parent_phone,
                    "final_error": str(error),
                    "enqueue_error": str(enqueue_err),
                    "retries_attempted": retry_count,
                }, indent=2, default=str),
            )
            return False

    # Retries exhausted → permanent DLQ.
    frappe.log_error(
        title=VOCALLABS_DLQ_LOG_TITLE,
        message=json.dumps({
            "student_id": pe.student,
            "pe_name": pe_name,
            "week": week,
            "escalation_order": escalation_order,
            "parent_phone": parent_phone,
            "final_error": str(error),
            "retries_attempted": retry_count,
        }, indent=2, default=str),
    )
    return False


# ════════════════════════════════════════════════════════════
# Misc
# ════════════════════════════════════════════════════════════


def _safe_summary(obj, max_len=500):
    """Truncate any JSON-serializable object for log-friendliness."""
    try:
        text = json.dumps(obj, default=str)
    except Exception:
        text = str(obj)
    if len(text) > max_len:
        return text[:max_len] + "...[truncated]"
    return text
