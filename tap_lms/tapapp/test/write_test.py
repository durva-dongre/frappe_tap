import concurrent.futures
import json
import time
import sys

import requests

BASE_URL = "http://127.0.0.1:8000"
API_PREFIX = "/api/method/"
ENDPOINT = "tap_lms.tapapp.api.progress.learner.record_activity"
SITE_HOST = "lms.site"


def call(session, learner_id, timeout=20):
    url = f"{BASE_URL}{API_PREFIX}{ENDPOINT}"
    headers = {"Host": SITE_HOST}
    t0 = time.time()
    try:
        resp = session.post(
            url,
            data={"learner_id": learner_id, "xp": 1, "activity_type": "writetest"},
            headers=headers,
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        return {"latency_ms": (time.time() - t0) * 1000.0, "status": None, "error": str(e), "body": None, "learner_id": learner_id}

    latency_ms = (time.time() - t0) * 1000.0
    try:
        body = resp.json()
    except ValueError:
        body = {"_raw": resp.text[:1000]}
    return {"latency_ms": latency_ms, "status": resp.status_code, "error": None, "body": body, "learner_id": learner_id}


def main():
    ids = [x.strip() for x in sys.argv[1].split(",") if x.strip()]
    concurrency = len(ids)

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=concurrency + 5, pool_maxsize=concurrency + 5)
    session.mount("http://", adapter)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(call, session, lid) for lid in ids]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    wall = time.time() - t0

    print(f"sent={len(results)} wall={wall:.2f}s")

    error_types = {}
    for r in results:
        if r["status"] and 200 <= r["status"] < 300 and isinstance(r["body"], dict) and r["body"].get("activity_recorded") is True:
            continue
        if isinstance(r["body"], dict):
            key = r["body"].get("exc_type") or r["error"] or f"status_{r['status']}"
        else:
            key = r["error"] or f"status_{r['status']}"
        error_types.setdefault(key, []).append(r)

    print(f"\ndistinct error types: {list(error_types.keys())}")
    for key, rows in error_types.items():
        print(f"\n--- {key} (count={len(rows)}) ---")
        sample = rows[0]
        print(f"learner_id={sample['learner_id']} status={sample['status']}")
        if isinstance(sample["body"], dict):
            print(json.dumps(sample["body"], indent=2)[:3000])
        else:
            print(sample["body"])


if __name__ == "__main__":
    main()