import pytest
import frappe
import json
from unittest.mock import patch, MagicMock
from tap_lms import glific_onboarding

# ------------------------------------------
# TEST: trigger_onboarding_flow
# ------------------------------------------
@patch("frappe.enqueue")
@patch("frappe.get_doc")
def test_trigger_onboarding_flow_success(mock_get_doc, mock_enqueue):
    # Mock onboarding stage & onboarding set
    stage_mock = MagicMock()
    stage_mock.is_active = True
    stage_mock.stage_flows = [MagicMock(student_status="assigned", glific_flow_id="flow123", flow_type="Group")]
    onboarding_mock = MagicMock()
    onboarding_mock.status = "Processed"

    # Mock frappe.get_doc return values
    mock_get_doc.side_effect = lambda doctype, name=None: stage_mock if doctype == "OnboardingStage" else onboarding_mock

    # Mock enqueue
    mock_enqueue.return_value = "job_123"

    result = glific_onboarding.trigger_onboarding_flow("onboard1", "stage1", student_status="assigned")
    assert result["success"]
    assert result["job_id"] == "job_123"

@patch("frappe.get_doc")
def test_trigger_onboarding_flow_stage_inactive(mock_get_doc):
    stage_mock = MagicMock()
    stage_mock.is_active = False
    onboarding_mock = MagicMock()
    onboarding_mock.status = "Processed"
    mock_get_doc.side_effect = lambda doctype, name=None: stage_mock if doctype == "OnboardingStage" else onboarding_mock

    with pytest.raises(frappe.ValidationError):
        glific_onboarding.trigger_onboarding_flow("onboard1", "stage1", student_status="assigned")

# ------------------------------------------
# TEST: _trigger_onboarding_flow_job
# ------------------------------------------
@patch("tap_lms.glific_onboarding.trigger_group_flow")
@patch("tap_lms.glific_onboarding.get_glific_auth_headers")
@patch("frappe.get_doc")
def test_trigger_onboarding_flow_job_group(mock_get_doc, mock_get_auth, mock_trigger_group):
    stage_mock = MagicMock()
    onboarding_mock = MagicMock()
    mock_get_doc.side_effect = lambda doctype, name=None: stage_mock if doctype == "OnboardingStage" else onboarding_mock

    mock_get_auth.return_value = {"authorization": "Bearer testtoken"}
    mock_trigger_group.return_value = {"status": "success"}

    result = glific_onboarding._trigger_onboarding_flow_job("onboard1", "stage1", "assigned", "flow123", "Group")
    assert result == {"status": "success"}

# ------------------------------------------
# TEST: trigger_group_flow
# ------------------------------------------
@patch("requests.post")
@patch("tap_lms.glific_onboarding.create_or_get_glific_group_for_batch")
@patch("frappe.get_doc")
def test_trigger_group_flow_success(mock_get_doc, mock_group, mock_post):
    onboarding_mock = MagicMock()
    stage_mock = MagicMock()
    contact_group = MagicMock()
    contact_group.group_id = "group123"

    mock_get_doc.side_effect = lambda doctype, name=None: contact_group if doctype == "GlificContactGroup" else MagicMock()
    mock_group.return_value = {"success": True}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {"startGroupFlow": {"success": True}}
    }
    mock_post.return_value = mock_response

    result = glific_onboarding.trigger_group_flow(onboarding_mock, stage_mock, "Bearer token", "assigned", "flow123")
    assert "group_flow_result" in result

# ------------------------------------------
# TEST: trigger_individual_flows
# ------------------------------------------
@patch("tap_lms.glific_onboarding.start_contact_flow")
@patch("tap_lms.glific_onboarding.get_students_from_onboarding")
def test_trigger_individual_flows_success(mock_get_students, mock_start_flow):
    student = MagicMock()
    student.name = "S1"
    student.name1 = "John"
    student.glific_id = "G123"
    mock_get_students.return_value = [student]
    mock_start_flow.return_value = True

    onboarding_mock = MagicMock()
    stage_mock = MagicMock()

    result = glific_onboarding.trigger_individual_flows(onboarding_mock, stage_mock, "Bearer token", "assigned", "flow123")
    assert result["individual_count"] == 1

# ------------------------------------------
# TEST: get_stage_flow_statuses
# ------------------------------------------
@patch("frappe.get_doc")
def test_get_stage_flow_statuses_new_structure(mock_get_doc):
    stage_mock = MagicMock()
    stage_mock.stage_flows = [MagicMock(student_status="assigned")]
    mock_get_doc.return_value = stage_mock

    result = glific_onboarding.get_stage_flow_statuses("stage1")
    assert result == {"statuses": ["assigned"]}

# ------------------------------------------
# TEST: get_students_from_onboarding
# ------------------------------------------
@patch("frappe.get_all")
@patch("frappe.get_doc")
def test_get_students_from_onboarding(mock_get_doc, mock_get_all):
    mock_get_all.return_value = [{"student_id": "S1"}]
    student_mock = MagicMock()
    mock_get_doc.return_value = student_mock

    onboarding_mock = MagicMock()
    onboarding_mock.name = "onboard1"
    result = glific_onboarding.get_students_from_onboarding(onboarding_mock, stage_name="stage1")
    assert isinstance(result, list)

# ------------------------------------------
# TEST: get_job_status
# ------------------------------------------
@patch("frappe.utils.background_jobs.get_job_status")
def test_get_job_status_complete(mock_status):
    mock_status.return_value = "finished"
    result = glific_onboarding.get_job_status("job123")
    assert "status" in result

# ------------------------------------------
# TEST: get_onboarding_progress_report
# ------------------------------------------
@patch("frappe.get_all")
@patch("frappe.get_doc")
def test_get_onboarding_progress_report(mock_get_doc, mock_get_all):
    mock_get_all.return_value = [
        {"name": "progress1", "student": "S1", "stage": "stage1", "status": "assigned"}
    ]
    student_mock = MagicMock()
    stage_mock = MagicMock()
    mock_get_doc.side_effect = lambda doctype, name=None: student_mock if doctype == "Student" else stage_mock

    result = glific_onboarding.get_onboarding_progress_report(stage="stage1")
    assert "summary" in result and "details" in result

# ------------------------------------------
# TEST: update_incomplete_stages
# ------------------------------------------
@patch("frappe.get_all")
@patch("frappe.get_doc")
def test_update_incomplete_stages(mock_get_doc, mock_get_all):
    mock_get_all.return_value = [{"name": "progress1", "student": "S1", "stage": "stage1"}]
    mock_progress = MagicMock()
    mock_get_doc.return_value = mock_progress

    glific_onboarding.update_incomplete_stages()
    mock_progress.save.assert_called_once()
