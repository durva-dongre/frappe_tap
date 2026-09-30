#!/bin/sh

# Run from ~/frappe-bench
# Usage: sh run_tapvoice_tests.sh

set -e

SITE="lms.site"
APP="tap_lms"

echo "=== 1. Enabling tests on ${SITE} (safe to re-run) ==="
bench --site "${SITE}" set-config allow_tests true

echo ""
echo "=== 2. Clearing cache ==="
bench --site "${SITE}" clear-cache

echo ""
echo "=== 3. Checking fixture file exists ==="
FIXTURE="apps/${APP}/${APP}/tapvoice/test/fixtures/content_hash_vectors.json"
if [ ! -f "$FIXTURE" ]; then
    echo "MISSING: $FIXTURE"
    echo "Copy the generated content_hash_vectors.json into that path before continuing."
    exit 1
fi
echo "found: $FIXTURE"

echo ""
echo "=== 4. Checking doctype folders are correctly named ==="
for name in tap_voice_settings tap_voice_run; do
    if [ ! -d "apps/${APP}/${APP}/${APP}/doctype/${name}" ]; then
        echo "MISSING doctype folder: ${name}"
        exit 1
    fi
done
echo "doctype folders OK"

echo ""
echo "=== 5. Running full tapvoice test module ==="
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.tapvoice.test.test_contract"
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.tapvoice.test.test_text"
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.tapvoice.test.test_tokens"
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.tapvoice.test.test_runpod_client"
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.tapvoice.test.test_eligibility"
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.tapvoice.test.test_planner_budget"
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.tapvoice.test.test_pod_api"
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.tapvoice.test.test_deploy"
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.tapvoice.test.test_reaper"

echo ""
echo "=== 6. Running doctype-level tests ==="
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.${APP}.doctype.tap_voice_run.test_tap_voice_run"
bench --site "${SITE}" run-tests --app "${APP}" --module "${APP}.${APP}.doctype.secrets.test_secrets"

echo ""
echo "=== ALL DONE ==="