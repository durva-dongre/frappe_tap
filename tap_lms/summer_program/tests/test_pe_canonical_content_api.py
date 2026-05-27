"""
Regression tests for task #71 (2026-05-23): PE-canonical reads in the
next-content read APIs.

Background
----------
`get_next_content` and `get_weekly_content` previously called
`_resolve_path(student, batch, bpr, current_week)` which recomputed
Core/Remedial from prior-week submission validity, completely ignoring
`pe.current_path` (which the state machine writes at T6b, T14, T8). Same
divergence risk for `tier` — recomputed from week/path lookup, ignoring
`pe.current_tier`.

Divergence scenarios where this matters
---------------------------------------
1. Student fails W1 AI validation → T6b fires → `pe.current_path = Remedial`.
   But `_resolve_path` for W1 returns `Core` (the short-circuit `if
   current_week <= 1: return PATH_CORE` was a separate bug — but also
   demonstrates the trust-the-state-machine principle).

2. T14 advances a Core-route student from W1→W2 → `pe.current_path = Core,
   pe.current_tier = Intermediate`. But if W1's submission was AI-flagged
   (still counts as submitted but invalid type), `_resolve_path` for W2
   would return `Remedial`. Pre-fix: student gets Remedial content for W2
   even though T14 explicitly put them on Core.

These tests pin the corrected behavior: read `pe.current_path` and
`pe.current_tier` directly; never recompute them in the read API.

Test strategy
-------------
Mock the lower-level helpers (resolve_student, _get_active_bpr_for_student,
_get_course_level_for_student, _get_learning_unit, etc.) so we exercise
only the path/tier-resolution branch. The tests assert that the
`_get_learning_unit` lookup is called with the PE-canonical (path, tier)
tuple, NOT with whatever `_resolve_path` would have computed.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock


def _fake_pe(name="pe-test-001", current_week=2, current_path="Core",
              current_tier="Intermediate", course_level="CL-001",
              glific_id="gl-test-001"):
    """Minimal PE-like object the next-content API reads from."""
    return frappe._dict({
        "name": name,
        "student": "STU-CANON-001",
        "batch": "palv2-test-CANON",
        "current_week": current_week,
        "current_path": current_path,
        "current_tier": current_tier,
        "course_level": course_level,
        "glific_id": glific_id,
        "language": "English",
    })


def _patch_chain(student_id, pe, batch_name="BATCH-CANON-001",
                  bpr_name="BPR-CANON-001", calendar_week=2):
    """Build the mock context that covers the boilerplate of get_next_content /
    get_weekly_content up to the path/tier resolution branch.

    Returns a list of patch objects to apply via contextlib.ExitStack — call
    sites can extend with any additional mocks they need.
    """
    student_doc = MagicMock(name=student_id)
    student_doc.archetype = "fence_sitter"
    student_doc.experiment_arm = "arm_a"

    batch_doc = MagicMock()
    batch_doc.name = batch_name
    batch_doc.total_weeks = 8
    batch_doc.current_calendar_week = calendar_week
    batch_doc.start_date = "2026-01-01"

    return {
        "student_doc": student_doc,
        "batch_doc": batch_doc,
        "bpr_name": bpr_name,
        "pe": pe,
        "calendar_week": calendar_week,
    }


class TestGetWeeklyContentPECanonical(FrappeTestCase):
    """get_weekly_content reads path + tier from PE, not from _resolve_path."""

    def test_uses_pe_current_path_remedial_over_recomputed_core(self):
        """PE says Remedial (T6b set it). _resolve_path would say Core for
        this current_week. Expect: API calls _get_learning_unit with
        path-derived tier 'Remedial', NOT the recomputed Core/Intermediate."""
        from tap_lms.summer_program import student_progression_sp as sp

        ctx = _patch_chain(
            student_id="STU-CANON-001",
            pe=_fake_pe(current_path="Remedial", current_tier="Remedial"),
        )

        with patch.object(sp, "_resolve_student_id", return_value="STU-CANON-001"), \
             patch.object(sp, "frappe") as mock_frappe, \
             patch.object(sp, "_get_active_bpr_for_student",
                          return_value=(ctx["batch_doc"], ctx["bpr_name"])), \
             patch.object(sp, "_get_course_level_for_student",
                          return_value="CL-001"), \
             patch.object(sp, "_get_current_week", return_value=ctx["calendar_week"]), \
             patch.object(sp, "get_active_pe", return_value=ctx["pe"]), \
             patch.object(sp, "_get_learning_unit",
                          return_value="LU-W2-Remedial") as mock_lu_lookup, \
             patch.object(sp, "_resolve_path", return_value="Core") as mock_resolve_path, \
             patch.object(sp, "_get_content_items",
                          return_value=[{"content_type": "VideoClass",
                                         "content_id": "VC-1",
                                         "content_name": "V1"}]), \
             patch.object(sp, "_get_week_rule",
                          return_value={"expected_submission_type": "text"}), \
             patch.object(sp, "_get_or_create_sp_progress",
                          return_value="SSP-test"):
            mock_frappe.get_doc.return_value = ctx["student_doc"]
            mock_frappe.db.get_value.return_value = "LU Display Name"
            mock_frappe.log_error = MagicMock()

            sp.get_weekly_content("STU-CANON-001", course_level="CL-001")

        # The LU lookup MUST have been called with (course_level=CL-001,
        # week=2, tier='Remedial') — NOT 'Intermediate'.
        mock_lu_lookup.assert_called()
        call_args = mock_lu_lookup.call_args.args
        course_level_arg, week_arg, tier_arg = call_args[0], call_args[1], call_args[2]
        self.assertEqual(course_level_arg, "CL-001")
        self.assertEqual(week_arg, 2)
        self.assertEqual(tier_arg, "Remedial",
                         "PE.current_tier='Remedial' MUST drive the LU lookup, "
                         "regardless of what _resolve_path would have computed")
        # _resolve_path must NOT have been called from the read path
        mock_resolve_path.assert_not_called()

    def test_uses_pe_current_path_core_over_recomputed_remedial(self):
        """The inverse: PE says Core (T14 set it). _resolve_path would say
        Remedial for this week. Expect: API uses Core."""
        from tap_lms.summer_program import student_progression_sp as sp

        ctx = _patch_chain(
            student_id="STU-CANON-002",
            pe=_fake_pe(current_path="Core", current_tier="Intermediate"),
        )

        with patch.object(sp, "_resolve_student_id", return_value="STU-CANON-002"), \
             patch.object(sp, "frappe") as mock_frappe, \
             patch.object(sp, "_get_active_bpr_for_student",
                          return_value=(ctx["batch_doc"], ctx["bpr_name"])), \
             patch.object(sp, "_get_course_level_for_student",
                          return_value="CL-001"), \
             patch.object(sp, "_get_current_week", return_value=ctx["calendar_week"]), \
             patch.object(sp, "get_active_pe", return_value=ctx["pe"]), \
             patch.object(sp, "_get_learning_unit",
                          return_value="LU-W2-Intermediate") as mock_lu_lookup, \
             patch.object(sp, "_resolve_path",
                          return_value="Remedial") as mock_resolve_path, \
             patch.object(sp, "_get_content_items",
                          return_value=[]), \
             patch.object(sp, "_get_week_rule",
                          return_value=None), \
             patch.object(sp, "_get_or_create_sp_progress",
                          return_value="SSP-test"):
            mock_frappe.get_doc.return_value = ctx["student_doc"]
            mock_frappe.db.get_value.return_value = "LU Display Name"
            mock_frappe.log_error = MagicMock()

            sp.get_weekly_content("STU-CANON-002", course_level="CL-001")

        call_args = mock_lu_lookup.call_args.args
        self.assertEqual(call_args[2], "Intermediate",
                         "PE.current_tier='Intermediate' MUST drive the LU "
                         "lookup, ignoring _resolve_path's recomputation")
        mock_resolve_path.assert_not_called()

    def test_returns_no_active_pe_when_pe_missing(self):
        """Defensive: if no active PE exists, return a clear error envelope
        instead of falling through to a stale-state computation.

        Note: get_weekly_content is decorated with @glific_response which
        writes the dict to frappe.local.response and returns None. Read the
        result from frappe.local.response (see utils.py:71-106).
        """
        from tap_lms.summer_program import student_progression_sp as sp

        ctx = _patch_chain(
            student_id="STU-CANON-003",
            pe=None,  # no active PE
        )

        # Reset frappe.local.response so we read only what this call writes.
        frappe.local.response = frappe._dict({})

        with patch.object(sp, "_resolve_student_id", return_value="STU-CANON-003"), \
             patch.object(sp, "frappe") as mock_frappe, \
             patch.object(sp, "_get_active_bpr_for_student",
                          return_value=(ctx["batch_doc"], ctx["bpr_name"])), \
             patch.object(sp, "_get_course_level_for_student",
                          return_value="CL-001"), \
             patch.object(sp, "_get_current_week", return_value=ctx["calendar_week"]), \
             patch.object(sp, "get_active_pe", return_value=None):
            mock_frappe.get_doc.return_value = ctx["student_doc"]
            mock_frappe.log_error = MagicMock()

            sp.get_weekly_content("STU-CANON-003", course_level="CL-001")

        # @glific_response wrote the dict here (the decorator's frappe is the
        # REAL frappe — utils.py's import is unpatched by this test).
        self.assertFalse(frappe.local.response.get("success", True))
        self.assertEqual(frappe.local.response.get("status"), "no_active_pe")


class TestGetNextContentPECanonical(FrappeTestCase):
    """get_next_content reads path + tier from PE, not from _resolve_path."""

    def test_week_advancement_wait_skips_normal_first_content_call(self):
        """First content calls are not in week_completed + week_advancement,
        so the wait helper must not sleep or reload."""
        from tap_lms.summer_program import student_progression_sp as sp

        pe = MagicMock()
        pe.resolved_flow_state = "normal_content_delivery"
        pe.next_action_type = ""

        with patch.object(sp.time, "sleep") as mock_sleep:
            result = sp._wait_for_week_advancement_if_pending(pe)

        self.assertTrue(result["completed"])
        self.assertEqual(result["pe"], pe)
        self.assertEqual(result["waited_seconds"], 0)
        mock_sleep.assert_not_called()
        pe.reload.assert_not_called()

    def test_week_advancement_wait_polls_every_four_seconds_until_complete(self):
        """When T13 has scheduled week_advancement, get_next_content should
        wait in 4-second intervals until the dispatcher clears the pending
        state."""
        from tap_lms.summer_program import student_progression_sp as sp
        from tap_lms.summer_program.constants import (
            ACTION_WEEK_ADVANCEMENT,
            STATE_NORMAL_CONTENT,
            STATE_WEEK_COMPLETED,
        )

        pe = MagicMock()
        pe.resolved_flow_state = STATE_WEEK_COMPLETED
        pe.next_action_type = ACTION_WEEK_ADVANCEMENT

        def advance_on_reload():
            pe.resolved_flow_state = STATE_NORMAL_CONTENT
            pe.next_action_type = ""
            pe.current_week = 2

        pe.reload.side_effect = advance_on_reload

        with patch.object(sp.time, "sleep") as mock_sleep:
            result = sp._wait_for_week_advancement_if_pending(pe)

        self.assertTrue(result["completed"])
        self.assertEqual(result["waited_seconds"], 4)
        mock_sleep.assert_called_once_with(4)
        pe.reload.assert_called_once()

    def test_week_advancement_wait_times_out_when_dispatcher_does_not_advance(self):
        """A stuck dispatcher row must not hold the request indefinitely."""
        from tap_lms.summer_program import student_progression_sp as sp
        from tap_lms.summer_program.constants import (
            ACTION_WEEK_ADVANCEMENT,
            STATE_WEEK_COMPLETED,
        )

        pe = MagicMock()
        pe.resolved_flow_state = STATE_WEEK_COMPLETED
        pe.next_action_type = ACTION_WEEK_ADVANCEMENT

        with patch.object(sp.time, "sleep") as mock_sleep:
            result = sp._wait_for_week_advancement_if_pending(
                pe,
                max_wait_seconds=8,
                poll_seconds=4,
            )

        self.assertFalse(result["completed"])
        self.assertEqual(result["waited_seconds"], 8)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(4)
        self.assertEqual(pe.reload.call_count, 2)

    def _mock_ssp_data(self, learning_unit, current_week, current_tier):
        """Build the StudentStageProgress dict the function reads after
        _get_or_create_sp_progress returns."""
        return {
            "name": "SSP-test",
            "student": "STU-CANON-N01",
            "stage": learning_unit,
            "status": "in_progress",
            "current_week": current_week,
            "current_tier": current_tier,
            "current_content_index": 0,
            "is_on_remedial": current_tier == "Remedial",
            "active_content_type": None,
            "active_content_id": None,
            "content_started_at": None,
            "active_quiz_attempt": None,
            "question_started_at": None,
            "course_context": "CL-001",
        }

    def test_uses_pe_current_path_remedial_for_next_content(self):
        """PE.current_path='Remedial' must drive the LU lookup even when
        _resolve_path would say Core."""
        from tap_lms.summer_program import student_progression_sp as sp

        ctx = _patch_chain(
            student_id="STU-CANON-N01",
            pe=_fake_pe(name="pe-canon-n01",
                       current_path="Remedial", current_tier="Remedial"),
        )
        ssp_data = self._mock_ssp_data(
            learning_unit="LU-W2-Remedial",
            current_week=2, current_tier="Remedial",
        )

        with patch.object(sp, "_resolve_student_id",
                          return_value="STU-CANON-N01"), \
             patch.object(sp, "frappe") as mock_frappe, \
             patch.object(sp, "_get_active_bpr_for_student",
                          return_value=(ctx["batch_doc"], ctx["bpr_name"])), \
             patch.object(sp, "_get_course_level_for_student",
                          return_value="CL-001"), \
             patch.object(sp, "_get_current_week",
                          return_value=ctx["calendar_week"]), \
             patch.object(sp, "_get_effective_week", return_value=2), \
             patch.object(sp, "get_active_pe", return_value=ctx["pe"]), \
             patch.object(sp, "_get_submission_validity",
                          return_value={"submitted": True, "is_valid": True}), \
             patch.object(sp, "_get_learning_unit",
                          return_value="LU-W2-Remedial") as mock_lu_lookup, \
             patch.object(sp, "_resolve_path",
                          return_value="Core") as mock_resolve_path, \
             patch.object(sp, "_get_or_create_sp_progress",
                          return_value="SSP-test"), \
             patch.object(sp, "_get_content_items",
                          return_value=[{"content_type": "VideoClass",
                                         "content_id": "VC-W2R-1",
                                         "content_name": "V"}]), \
             patch.object(sp, "_get_video_assessments", return_value=[]), \
             patch.object(sp, "_get_learning_unit_info",
                          return_value={"name": "LU display"}):
            mock_frappe.get_doc.return_value = ctx["student_doc"]
            mock_frappe.db.get_value.return_value = ssp_data
            mock_frappe.log_error = MagicMock()

            sp.get_next_content("STU-CANON-N01")

        # LU lookup used Remedial tier from PE, not Intermediate from week-rule
        call_args = mock_lu_lookup.call_args.args
        self.assertEqual(call_args[2], "Remedial",
                         "PE.current_tier='Remedial' MUST drive the LU lookup")
        mock_resolve_path.assert_not_called()

    def test_uses_pe_current_path_core_for_next_content(self):
        """The inverse direction: PE.current_path='Core' must drive the LU
        lookup even when _resolve_path would say Remedial."""
        from tap_lms.summer_program import student_progression_sp as sp

        ctx = _patch_chain(
            student_id="STU-CANON-N02",
            pe=_fake_pe(name="pe-canon-n02",
                       current_path="Core", current_tier="Intermediate"),
        )
        ssp_data = self._mock_ssp_data(
            learning_unit="LU-W2-Intermediate",
            current_week=2, current_tier="Intermediate",
        )

        with patch.object(sp, "_resolve_student_id",
                          return_value="STU-CANON-N02"), \
             patch.object(sp, "frappe") as mock_frappe, \
             patch.object(sp, "_get_active_bpr_for_student",
                          return_value=(ctx["batch_doc"], ctx["bpr_name"])), \
             patch.object(sp, "_get_course_level_for_student",
                          return_value="CL-001"), \
             patch.object(sp, "_get_current_week",
                          return_value=ctx["calendar_week"]), \
             patch.object(sp, "_get_effective_week", return_value=2), \
             patch.object(sp, "get_active_pe", return_value=ctx["pe"]), \
             patch.object(sp, "_get_submission_validity",
                          return_value={"submitted": True, "is_valid": False}), \
             patch.object(sp, "_get_learning_unit",
                          return_value="LU-W2-Intermediate") as mock_lu_lookup, \
             patch.object(sp, "_resolve_path",
                          return_value="Remedial") as mock_resolve_path, \
             patch.object(sp, "_get_or_create_sp_progress",
                          return_value="SSP-test"), \
             patch.object(sp, "_get_content_items",
                          return_value=[{"content_type": "VideoClass",
                                         "content_id": "VC-W2I-1",
                                         "content_name": "V"}]), \
             patch.object(sp, "_get_video_assessments", return_value=[]), \
             patch.object(sp, "_get_learning_unit_info",
                          return_value={"name": "LU display"}):
            mock_frappe.get_doc.return_value = ctx["student_doc"]
            mock_frappe.db.get_value.return_value = ssp_data
            mock_frappe.log_error = MagicMock()

            sp.get_next_content("STU-CANON-N02")

        call_args = mock_lu_lookup.call_args.args
        self.assertEqual(call_args[2], "Intermediate",
                         "PE.current_tier='Intermediate' MUST drive the LU "
                         "lookup, ignoring _resolve_path's recomputation")
        mock_resolve_path.assert_not_called()

    def test_no_active_pe_returns_error_envelope(self):
        """When no PE is found, get_next_content returns a clear status
        instead of crashing or returning stale state.

        Note: get_next_content is decorated with @glific_response which
        writes the dict to frappe.local.response and returns None. Read the
        result from frappe.local.response (see utils.py:71-106).
        """
        from tap_lms.summer_program import student_progression_sp as sp

        ctx = _patch_chain(
            student_id="STU-CANON-N03",
            pe=None,
        )

        # Reset frappe.local.response so we read only what this call writes.
        frappe.local.response = frappe._dict({})

        with patch.object(sp, "_resolve_student_id",
                          return_value="STU-CANON-N03"), \
             patch.object(sp, "frappe") as mock_frappe, \
             patch.object(sp, "_get_active_bpr_for_student",
                          return_value=(ctx["batch_doc"], ctx["bpr_name"])), \
             patch.object(sp, "_get_course_level_for_student",
                          return_value="CL-001"), \
             patch.object(sp, "_get_current_week",
                          return_value=ctx["calendar_week"]), \
             patch.object(sp, "get_active_pe", return_value=None):
            mock_frappe.get_doc.return_value = ctx["student_doc"]
            mock_frappe.log_error = MagicMock()

            sp.get_next_content("STU-CANON-N03")

        # @glific_response wrote the dict here (the decorator's frappe is the
        # REAL frappe — utils.py's import is unpatched by this test).
        self.assertFalse(frappe.local.response.get("success", True))
        self.assertEqual(frappe.local.response.get("status"), "no_active_pe")


class TestSspCanonicalAutoCorrect(FrappeTestCase):
    """CR-008 extension (2026-05-23): SSP-canonical auto-correct in
    get_next_content's progression cursor.

    The legacy trigger only caught LU drift ("stage mismatch"). It missed:

      1. SSP.current_week behind PE.current_week — complete_content can
         lag behind T14's PE advance, leaving SSP pointing at the old
         week's content list.

      2. New week just started (pe.weekly_video_done = 0, T14's lazy-reset
         trigger signal) AND SSP.current_content_index > 0 — observed in
         ST00051359: SSP.content_index was 1 (Quiz) but pe.weekly_video_done
         was 0, meaning the student hadn't watched the W2 Video yet. The
         API was about to serve the Quiz, skipping the Video entirely.

    Both new triggers converge on the same reset: align SSP.current_week
    to PE.current_week, set content_index = 0, update stage/tier.
    """

    def _build_mocks(self, ssp_data, pe, stage_already_matches=True):
        """Helper that wraps the long patch.object chain used by these
        tests. Returns the ExitStack and the mock_lu_lookup for assertion."""
        from tap_lms.summer_program import student_progression_sp as sp

        student_doc = MagicMock(name="STU-SSP-001")
        student_doc.archetype = "fence_sitter"
        student_doc.experiment_arm = "arm_a"

        batch_doc = MagicMock()
        batch_doc.name = "BATCH-SSP-001"
        batch_doc.total_weeks = 8
        batch_doc.current_calendar_week = 2

        # If we want the stage to match the computed LU, return the same
        # value as is in ssp_data.stage. Otherwise return something different
        # so the stage-mismatch branch fires.
        computed_lu = (ssp_data["stage"] if stage_already_matches
                       else "LU-DIFFERENT")
        return sp, student_doc, batch_doc, computed_lu

    def test_week_mismatch_triggers_reset(self):
        """SSP.current_week behind PE.current_week (and stage matches) →
        auto-correct fires, aligns SSP.current_week, resets content_index."""
        from tap_lms.summer_program import student_progression_sp as sp

        ssp_data = {
            "name": "SSP-CANON-W",
            "student": "STU-SSP-W",
            "stage": "LU-W2-Intermediate",     # matches computed
            "status": "in_progress",
            "current_week": 1,                  # ← STALE — PE is at 2
            "current_tier": "Basic",
            "current_content_index": 1,         # past 0
            "is_on_remedial": False,
            "active_content_type": None,
            "active_content_id": None,
            "content_started_at": None,
            "active_quiz_attempt": None,
            "question_started_at": None,
            "course_context": "CL-001",
        }
        pe = _fake_pe(current_week=2, current_path="Core",
                       current_tier="Intermediate")

        student_doc = MagicMock(name="STU-SSP-W")
        student_doc.archetype = "fence_sitter"
        student_doc.experiment_arm = "arm_a"

        batch_doc = MagicMock()
        batch_doc.name = "BATCH-SSP-001"
        batch_doc.total_weeks = 8
        batch_doc.current_calendar_week = 2

        with patch.object(sp, "_resolve_student_id", return_value="STU-SSP-W"), \
             patch.object(sp, "frappe") as mock_frappe, \
             patch.object(sp, "_get_active_bpr_for_student",
                          return_value=(batch_doc, "BPR-001")), \
             patch.object(sp, "_get_course_level_for_student",
                          return_value="CL-001"), \
             patch.object(sp, "_get_current_week", return_value=2), \
             patch.object(sp, "_get_effective_week", return_value=2), \
             patch.object(sp, "get_active_pe", return_value=pe), \
             patch.object(sp, "_get_submission_validity",
                          return_value={"submitted": True, "is_valid": True}), \
             patch.object(sp, "_get_learning_unit",
                          return_value="LU-W2-Intermediate"), \
             patch.object(sp, "_get_or_create_sp_progress",
                          return_value="SSP-CANON-W"), \
             patch.object(sp, "_get_content_items",
                          return_value=[{"content_type": "VideoClass",
                                         "content_id": "VC-W2-1",
                                         "content_name": "V1"}]), \
             patch.object(sp, "_get_video_assessments", return_value=[]), \
             patch.object(sp, "_get_learning_unit_info",
                          return_value={"name": "LU display"}):
            mock_frappe.get_doc.return_value = student_doc
            mock_frappe.db.get_value.return_value = ssp_data
            mock_frappe.db.set_value = MagicMock()
            mock_frappe.log_error = MagicMock()

            sp.get_next_content("STU-SSP-W")

            # frappe.db.set_value MUST have been called with the SSP reset payload
            set_value_calls = [
                c for c in mock_frappe.db.set_value.call_args_list
                if c.args and c.args[0] == "StudentStageProgress"
            ]
            self.assertTrue(set_value_calls,
                            "auto-correct must fire on week mismatch")
            # Verify the reset payload includes current_week alignment
            payload = set_value_calls[0].args[2]
            self.assertEqual(payload["current_week"], 2,
                             "SSP.current_week aligned to PE.current_week")
            self.assertEqual(payload["current_content_index"], 0,
                             "content_index reset to 0")

    def test_new_week_with_advanced_content_index_triggers_reset(self):
        """ST00051359's exact scenario: pe.weekly_video_done=0 (T14 just
        fired, expecting first video) AND SSP.current_content_index > 0
        (somehow advanced past the Video to the Quiz). API must reset
        content_index to 0 so the student gets the Video FIRST."""
        from tap_lms.summer_program import student_progression_sp as sp

        ssp_data = {
            "name": "SSP-CANON-NVY",
            "student": "STU-SSP-NVY",
            "stage": "LU-W2-Intermediate",   # matches — stage is NOT the trigger
            "status": "in_progress",
            "current_week": 2,                # matches PE — NOT the trigger
            "current_tier": "Intermediate",
            "current_content_index": 1,       # ← past 0, expecting Quiz
            "is_on_remedial": False,
            "active_content_type": "Quiz",
            "active_content_id": "Quiz-W2",
            "content_started_at": None,
            "active_quiz_attempt": None,
            "question_started_at": None,
            "course_context": "CL-001",
        }
        # pe.weekly_video_done = 0 → new-week-no-video-yet signal
        pe = _fake_pe(current_week=2, current_path="Core",
                       current_tier="Intermediate")
        pe["weekly_video_done"] = 0

        student_doc = MagicMock(name="STU-SSP-NVY")
        student_doc.archetype = "fence_sitter"
        student_doc.experiment_arm = "arm_a"

        batch_doc = MagicMock()
        batch_doc.name = "BATCH-SSP-001"
        batch_doc.total_weeks = 8
        batch_doc.current_calendar_week = 2

        with patch.object(sp, "_resolve_student_id", return_value="STU-SSP-NVY"), \
             patch.object(sp, "frappe") as mock_frappe, \
             patch.object(sp, "_get_active_bpr_for_student",
                          return_value=(batch_doc, "BPR-001")), \
             patch.object(sp, "_get_course_level_for_student",
                          return_value="CL-001"), \
             patch.object(sp, "_get_current_week", return_value=2), \
             patch.object(sp, "_get_effective_week", return_value=2), \
             patch.object(sp, "get_active_pe", return_value=pe), \
             patch.object(sp, "_get_submission_validity",
                          return_value={"submitted": True, "is_valid": True}), \
             patch.object(sp, "_get_learning_unit",
                          return_value="LU-W2-Intermediate"), \
             patch.object(sp, "_get_or_create_sp_progress",
                          return_value="SSP-CANON-NVY"), \
             patch.object(sp, "_get_content_items",
                          return_value=[
                              {"content_type": "VideoClass",
                               "content_id": "VC-W2-1",
                               "content_name": "Video"},
                              {"content_type": "Quiz",
                               "content_id": "Quiz-W2",
                               "content_name": "Quiz"},
                          ]), \
             patch.object(sp, "_get_video_assessments", return_value=[]), \
             patch.object(sp, "_get_learning_unit_info",
                          return_value={"name": "LU display"}):
            mock_frappe.get_doc.return_value = student_doc
            mock_frappe.db.get_value.return_value = ssp_data
            mock_frappe.db.set_value = MagicMock()
            mock_frappe.log_error = MagicMock()

            response = sp.get_next_content("STU-SSP-NVY")

            # Auto-correct should fire and reset content_index
            set_value_calls = [
                c for c in mock_frappe.db.set_value.call_args_list
                if c.args and c.args[0] == "StudentStageProgress"
            ]
            self.assertTrue(set_value_calls,
                            "auto-correct must fire when "
                            "weekly_video_done=0 AND content_index>0")
            payload = set_value_calls[0].args[2]
            self.assertEqual(payload["current_content_index"], 0,
                             "content_index reset to 0 — student gets the "
                             "Video FIRST, not the Quiz")

    def test_synced_ssp_does_not_trigger_reset(self):
        """Regression guard: when SSP is already in sync with PE (stage
        matches, week matches, weekly_video_done=1 or content_index=0),
        the auto-correct must NOT fire. We don't want gratuitous SSP
        writes on every read."""
        from tap_lms.summer_program import student_progression_sp as sp

        ssp_data = {
            "name": "SSP-CANON-SYNC",
            "student": "STU-SSP-SYNC",
            "stage": "LU-W2-Intermediate",
            "status": "in_progress",
            "current_week": 2,
            "current_tier": "Intermediate",
            "current_content_index": 1,       # past 0, but weekly_video_done=1
            "is_on_remedial": False,
            "active_content_type": "Quiz",
            "active_content_id": "Quiz-W2",
            "content_started_at": None,
            "active_quiz_attempt": None,
            "question_started_at": None,
            "course_context": "CL-001",
        }
        pe = _fake_pe(current_week=2, current_path="Core",
                       current_tier="Intermediate")
        pe["weekly_video_done"] = 1   # video already watched this week

        student_doc = MagicMock(name="STU-SSP-SYNC")
        student_doc.archetype = "fence_sitter"
        student_doc.experiment_arm = "arm_a"

        batch_doc = MagicMock()
        batch_doc.name = "BATCH-SSP-001"
        batch_doc.total_weeks = 8
        batch_doc.current_calendar_week = 2

        with patch.object(sp, "_resolve_student_id", return_value="STU-SSP-SYNC"), \
             patch.object(sp, "frappe") as mock_frappe, \
             patch.object(sp, "_get_active_bpr_for_student",
                          return_value=(batch_doc, "BPR-001")), \
             patch.object(sp, "_get_course_level_for_student",
                          return_value="CL-001"), \
             patch.object(sp, "_get_current_week", return_value=2), \
             patch.object(sp, "_get_effective_week", return_value=2), \
             patch.object(sp, "get_active_pe", return_value=pe), \
             patch.object(sp, "_get_submission_validity",
                          return_value={"submitted": True, "is_valid": True}), \
             patch.object(sp, "_get_learning_unit",
                          return_value="LU-W2-Intermediate"), \
             patch.object(sp, "_get_or_create_sp_progress",
                          return_value="SSP-CANON-SYNC"), \
             patch.object(sp, "_get_content_items",
                          return_value=[
                              {"content_type": "VideoClass",
                               "content_id": "VC-W2-1",
                               "content_name": "Video"},
                              {"content_type": "Quiz",
                               "content_id": "Quiz-W2",
                               "content_name": "Quiz"},
                          ]), \
             patch.object(sp, "_get_video_assessments", return_value=[]), \
             patch.object(sp, "_get_learning_unit_info",
                          return_value={"name": "LU display"}):
            mock_frappe.get_doc.return_value = student_doc
            mock_frappe.db.get_value.return_value = ssp_data
            mock_frappe.db.set_value = MagicMock()
            mock_frappe.log_error = MagicMock()

            sp.get_next_content("STU-SSP-SYNC")

            # The "auto-correct" set_value with a multi-field payload must
            # NOT have fired (it would include "current_content_index": 0).
            # Other set_value calls happen later (active_content_type write),
            # but the auto-correct's reset payload is distinct.
            auto_correct_calls = [
                c for c in mock_frappe.db.set_value.call_args_list
                if c.args and c.args[0] == "StudentStageProgress"
                and isinstance(c.args[2], dict)
                and c.args[2].get("current_content_index") == 0
                and "stage" in c.args[2]
            ]
            self.assertEqual(len(auto_correct_calls), 0,
                             "synced SSP must NOT trigger auto-correct reset")
