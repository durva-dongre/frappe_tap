import json

import frappe
import requests


class RunPodError(Exception):
    pass


class AmbiguousCreateError(RunPodError):
    pass


def _redact(env):
    return {key: "***" for key in env}


class RunPodClient:
    def __init__(self, settings, secrets):
        self.base = settings.runpod_api_base.rstrip("/")
        self.timeout = settings.http_timeout_seconds
        self.headers = {
            "Authorization": f"Bearer {secrets.get('runpod_api_key')}",
            "Content-Type": "application/json",
        }

    def create(self, payload):
        try:
            response = requests.post(
                f"{self.base}/pods",
                headers=self.headers,
                data=json.dumps(payload),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AmbiguousCreateError(str(exc)) from exc
        if response.status_code >= 500:
            raise AmbiguousCreateError(f"http_{response.status_code}")
        if response.status_code >= 400:
            raise RunPodError(f"http_{response.status_code}: {response.text[:300]}")
        return response.json()

    def find_by_name(self, name):
        try:
            response = requests.get(
                f"{self.base}/pods",
                headers=self.headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RunPodError(str(exc)) from exc
        if response.status_code >= 400:
            raise RunPodError(f"http_{response.status_code}")
        for pod in response.json().get("pods", []):
            if pod.get("name") == name:
                return pod
        return None

    def delete(self, pod_id):
        try:
            response = requests.delete(
                f"{self.base}/pods/{pod_id}", headers=self.headers, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise RunPodError(str(exc)) from exc
        return response.status_code < 300 or response.status_code == 404

    def stop(self, pod_id):
        try:
            response = requests.post(
                f"{self.base}/pods/{pod_id}/stop", headers=self.headers, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise RunPodError(str(exc)) from exc
        return response.status_code < 300