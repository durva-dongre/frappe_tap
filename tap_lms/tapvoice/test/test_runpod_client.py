import unittest
from unittest.mock import MagicMock

from tap_lms.tapvoice.lib.runpod import RunPodClient, RunPodError, build_create_payload


class FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else {}
        self.text = text
        self.content = text.encode("utf-8") if text else b"{}"

    def json(self):
        return self._json_body


class TestRunPodClient(unittest.TestCase):
    def _client(self):
        client = RunPodClient("https://rest.runpod.io/v1", "fake-key", timeout_seconds=5)
        client.session = MagicMock()
        return client

    def test_create_pod_success(self):
        client = self._client()
        client.session.request.return_value = FakeResponse(200, {"id": "pod-1", "costPerHr": 0.34})
        result = client.create_pod({"name": "run-1"})
        self.assertEqual(result["id"], "pod-1")

    def test_4xx_raises_runpod_error(self):
        client = self._client()
        client.session.request.return_value = FakeResponse(400, text="bad request")
        with self.assertRaises(RunPodError) as ctx:
            client.create_pod({"name": "run-1"})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_get_pod_404_returns_none(self):
        client = self._client()
        client.session.request.return_value = FakeResponse(404, text="not found")
        self.assertIsNone(client.get_pod("missing-pod"))

    def test_delete_pod_404_is_treated_as_success(self):
        client = self._client()
        client.session.request.return_value = FakeResponse(404, text="not found")
        self.assertTrue(client.delete_pod("missing-pod"))

    def test_find_by_name_matches(self):
        client = self._client()
        client.session.request.return_value = FakeResponse(
            200, {"pods": [{"id": "pod-1", "name": "run-1"}, {"id": "pod-2", "name": "run-2"}]}
        )
        found = client.find_by_name("run-2")
        self.assertEqual(found["id"], "pod-2")

    def test_find_by_name_no_match(self):
        client = self._client()
        client.session.request.return_value = FakeResponse(200, {"pods": []})
        self.assertIsNone(client.find_by_name("run-x"))


class FakeSettings:
    image_name = "repo/image:sha123"
    gpu_type_ids = ["NVIDIA RTX A5000"]
    gpu_count = 1
    container_disk_gb = 40
    volume_gb = 0
    interruptible = False
    cloud_type = ""
    registry_auth_id = ""
    data_center_ids = []
    allowed_cuda_versions = []


class TestBuildCreatePayload(unittest.TestCase):
    def test_minimal_payload_shape(self):
        payload = build_create_payload(FakeSettings(), "RUN-1", {"A": "1"})
        self.assertEqual(payload["name"], "RUN-1")
        self.assertEqual(payload["imageName"], "repo/image:sha123")
        self.assertEqual(payload["gpuTypeIds"], ["NVIDIA RTX A5000"])
        self.assertNotIn("cloudType", payload)
        self.assertNotIn("containerRegistryAuthId", payload)

    def test_optional_fields_included_when_set(self):
        settings = FakeSettings()
        settings.cloud_type = "Secure"
        settings.registry_auth_id = "auth-1"
        settings.data_center_ids = ["US-CA"]
        payload = build_create_payload(settings, "RUN-1", {})
        self.assertEqual(payload["cloudType"], "Secure")
        self.assertEqual(payload["containerRegistryAuthId"], "auth-1")
        self.assertEqual(payload["dataCenterIds"], ["US-CA"])
