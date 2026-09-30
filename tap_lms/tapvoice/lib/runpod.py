import requests


class RunPodError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class RunPodClient:
    def __init__(self, base_url, api_key, timeout_seconds=20):
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    def _request(self, method, path, **kwargs):
        try:
            response = self.session.request(
                method, f"{self.base}{path}", timeout=self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise RunPodError(f"request_error {exc}") from exc
        return response

    def create_pod(self, payload):
        response = self._request("POST", "/pods", json=payload)
        if response.status_code >= 400:
            raise RunPodError(f"http_{response.status_code} {response.text[:300]}", response.status_code)
        return response.json()

    def get_pod(self, pod_id):
        response = self._request("GET", f"/pods/{pod_id}")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise RunPodError(f"http_{response.status_code} {response.text[:300]}", response.status_code)
        return response.json()

    def find_by_name(self, name):
        response = self._request("GET", "/pods")
        if response.status_code >= 400:
            raise RunPodError(f"http_{response.status_code} {response.text[:300]}", response.status_code)
        for pod in response.json().get("pods", []):
            if pod.get("name") == name:
                return pod
        return None

    def delete_pod(self, pod_id):
        response = self._request("DELETE", f"/pods/{pod_id}")
        return response.status_code < 300 or response.status_code == 404

    def stop_pod(self, pod_id):
        response = self._request("POST", f"/pods/{pod_id}/stop")
        return response.status_code < 300

    def ping(self):
        response = self._request("GET", "/pods")
        if response.status_code >= 400:
            raise RunPodError(f"http_{response.status_code}", response.status_code)
        return True


def build_create_payload(settings, run_name, env):
    payload = {
        "name": run_name,
        "imageName": settings.image_name,
        "gpuTypeIds": list(settings.gpu_type_ids or []),
        "gpuCount": settings.gpu_count,
        "containerDiskInGb": settings.container_disk_gb,
        "volumeInGb": settings.volume_gb,
        "interruptible": bool(settings.interruptible),
        "env": dict(env or {}),
    }
    if settings.cloud_type:
        payload["cloudType"] = settings.cloud_type
    if settings.registry_auth_id:
        payload["containerRegistryAuthId"] = settings.registry_auth_id
    if settings.data_center_ids:
        payload["dataCenterIds"] = list(settings.data_center_ids)
    if settings.allowed_cuda_versions:
        payload["allowedCudaVersions"] = list(settings.allowed_cuda_versions)
    return payload