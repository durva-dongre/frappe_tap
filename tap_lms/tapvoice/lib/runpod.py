import requests


class RunPodError(Exception):
    def __init__(self, summary, status_code=None):
        super().__init__(summary)
        self.summary = summary
        self.status_code = status_code


class RunPodClient:
    def __init__(self, api_base, api_key, timeout_seconds=20):
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    def _request(self, method, path, **kwargs):
        url = f"{self.api_base}{path}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise RunPodError(f"request_error {type(exc).__name__}") from exc
        if response.status_code >= 400:
            body = response.text[:300] if response.text else ""
            raise RunPodError(f"http_{response.status_code} {body}", response.status_code)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise RunPodError("bad_json_response") from exc

    def create_pod(self, payload):
        return self._request("POST", "/pods", json=payload)

    def get_pod(self, pod_id):
        try:
            return self._request("GET", f"/pods/{pod_id}")
        except RunPodError as exc:
            if exc.status_code == 404:
                return None
            raise

    def list_pods(self):
        pods = self._request("GET", "/pods")
        return pods if isinstance(pods, list) else pods.get("pods", [])

    def ping(self):
        self.list_pods()
        return True

    def find_by_name(self, name):
        for pod in self.list_pods():
            if pod.get("name") == name:
                return pod
        return None

    def delete_pod(self, pod_id):
        try:
            self._request("DELETE", f"/pods/{pod_id}")
            return True
        except RunPodError as exc:
            if exc.status_code == 404:
                return True
            raise

    def stop_pod(self, pod_id):
        try:
            self._request("POST", f"/pods/{pod_id}/stop")
            return True
        except RunPodError as exc:
            if exc.status_code == 404:
                return True
            raise


def build_create_payload(settings, run_name, env, image_override=None):
    payload = {
        "name": run_name,
        "imageName": image_override or settings.image_name,
        "gpuTypeIds": list(settings.gpu_type_ids),
        "gpuCount": settings.gpu_count,
        "containerDiskInGb": settings.container_disk_gb,
        "volumeInGb": settings.volume_gb,
        "env": env,
        "interruptible": settings.interruptible,
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