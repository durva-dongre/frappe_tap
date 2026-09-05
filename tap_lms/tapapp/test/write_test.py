import argparse
import concurrent.futures
import json
import statistics
import sys
import time

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
        return {"latency_ms": (time.time() - t0) * 1000.0, "status": None, "error": str(e), "body": None}

    latency_ms = (time.time() - t0) * 1000.0
    try:
        body = resp.json()
    except ValueError:
        body = {"_raw": resp.text[:500]}
    return {"latency_ms": latency_ms, "status": resp.status_code, "error": None, "body": body}


def is_cap_error(result):
    body = result["body"]
    if not isinstance(body, dict):
        return False
    msg = str(body.get("message") or body.get("exc") or "")
    return "Weekly activity limit reached" in msg


def summarize(results, wall_clock_s):
    latencies = [r["latency_ms"] for r in results]
    success = sum(1 for r in results if r["status"] and 200 <= r["status"] < 300
                  and isinstance(r["body"], dict) and r["body"].get("activity_recorded") is True)
    cap_hits = sum(1 for r in results if is_cap_error(r))
    other_fail = len(results) - success - cap_hits

    print(f"  requests sent:      {len(results)}")
    print(f"  wall clock:         {wall_clock_s:.3f}s")
    print(f"  throughput:         {len(results) / wall_clock_s:.1f} req/s")
    print(f"  succeeded:          {success}")
    print(f"  weekly-cap 417s:    {cap_hits}  (expected/legitimate, not a bug)")
    print(f"  other failures:     {other_fail}")
    if latencies:
        print(f"  latency min/mean/max: {min(latencies):.1f}ms / {statistics.mean(latencies):.1f}ms / {max(latencies):.1f}ms")
    if other_fail:
        for r in results:
            if r["error"] or (r["status"] and not (200 <= r["status"] < 300)):
                if not is_cap_error(r):
                    print(f"    sample failure: status={r['status']} error={r['error']} body={r['body']}")
                    break


def test_same_row(learner_id, concurrency):
    print(f"\n=== SAME-ROW test: {concurrency} concurrent writers, all hitting learner_id={learner_id} ===")
    print("This is the worst case — every thread fights over one row's DB lock.")
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=concurrency + 5, pool_maxsize=concurrency + 5)
    session.mount("http://", adapter)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(call, session, learner_id) for _ in range(concurrency)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    wall = time.time() - t0
    summarize(results, wall)


def test_distinct_rows(learner_ids, concurrency, requests_per_learner):
    total = concurrency * requests_per_learner
    print(f"\n=== DISTINCT-ROW test: {concurrency} learners x {requests_per_learner} req each = {total} total ===")
    print("This is the real scaling case — each concurrent user only touches their own row.")
    if len(learner_ids) < concurrency:
        print(f"  WARNING: you gave {len(learner_ids)} learner_ids but asked for concurrency={concurrency}; "
              f"reusing ids means some threads WILL collide on the same row. Pass more --learner-ids "
              f"or lower --concurrency for a clean distinct-row test.")

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=concurrency + 5, pool_maxsize=concurrency + 5)
    session.mount("http://", adapter)

    jobs = []
    for i in range(concurrency):
        lid = learner_ids[i % len(learner_ids)]
        for _ in range(requests_per_learner):
            jobs.append(lid)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(call, session, lid) for lid in jobs]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    wall = time.time() - t0
    summarize(results, wall)


def main():
    p = argparse.ArgumentParser(description="Fast isolated write-concurrency test for record_activity")
    p.add_argument("--mode", choices=["same-row", "distinct-rows", "both"], default="both")
    p.add_argument("--learner-id", default="TL00000001", help="single learner_id for same-row test")
    p.add_argument("--learner-ids", default="", help="comma-separated learner_ids for distinct-rows test")
    p.add_argument("--concurrency", type=int, default=20)
    p.add_argument("--requests-per-learner", type=int, default=1)
    args = p.parse_args()

    if args.mode in ("same-row", "both"):
        test_same_row(args.learner_id, args.concurrency)

    if args.mode in ("distinct-rows", "both"):
        ids = [x.strip() for x in args.learner_ids.split(",") if x.strip()]
        if not ids:
            print("\n(skipping distinct-rows test — pass --learner-ids id1,id2,id3,... "
                  "with at least as many ids as --concurrency)", file=sys.stderr)
        else:
            test_distinct_rows(ids, args.concurrency, args.requests_per_learner)


if __name__ == "__main__":
    main()