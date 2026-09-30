#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:?usage: restructure_tapvoice.sh /path/to/repo}"
PKG="$REPO_ROOT/tap_lms/tapvoice"

test -d "$PKG" || { echo "missing $PKG"; exit 1; }

move() {
  src="$1"
  dst="$2"
  if git -C "$REPO_ROOT" mv "$src" "$dst" 2>/dev/null; then
    return 0
  fi
  mv "$src" "$dst"
  git -C "$REPO_ROOT" add "$dst" 2>/dev/null || true
}

remove() {
  target="$1"
  if git -C "$REPO_ROOT" rm -f "$target" 2>/dev/null; then
    return 0
  fi
  rm -f "$target"
}

mkdir -p "$PKG/lib" "$PKG/job" "$PKG/api" "$PKG/test/fixtures"

touch "$PKG/lib/__init__.py" "$PKG/job/__init__.py" "$PKG/api/__init__.py"

LIB_FILES="settings secrets languages text contract eligibility planner budget runpod tokens guard runstate runlog accounting breaker"
for f in $LIB_FILES; do
  if [ -f "$PKG/$f.py" ]; then
    move "$PKG/$f.py" "$PKG/lib/$f.py"
  fi
done

JOB_FILES="start deploy reaper termination reconcile recover"
for f in $JOB_FILES; do
  if [ -f "$PKG/$f.py" ]; then
    move "$PKG/$f.py" "$PKG/job/$f.py"
  fi
done

API_FILES="pod operator"
for f in $API_FILES; do
  if [ -f "$PKG/$f.py" ]; then
    move "$PKG/$f.py" "$PKG/api/$f.py"
  fi
done

if [ -d "$PKG/tests" ] && [ ! -d "$PKG/test" ]; then
  move "$PKG/tests" "$PKG/test"
fi
mkdir -p "$PKG/test/fixtures"
touch "$PKG/test/__init__.py"

find "$REPO_ROOT/tap_lms/tap_lms/doctype" -iname "*voice copy*" -print0 2>/dev/null | while IFS= read -r -d '' f; do
  remove "$f"
done
find "$REPO_ROOT" -iname "*voices copy*" -print0 2>/dev/null | while IFS= read -r -d '' f; do
  remove "$f"
done

if [ -f "$REPO_ROOT/pod/tests/test_storage_local.py" ] && [ ! -s "$REPO_ROOT/pod/tests/test_storage_local.py" ]; then
  remove "$REPO_ROOT/pod/tests/test_storage_local.py"
fi

grep -RIl "tap_lms\.tapvoice\." "$REPO_ROOT/tap_lms" 2>/dev/null | while read -r file; do
  python3 - "$file" << 'PYEOF'
import re, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    text = fh.read()
original = text
for name in ["settings","secrets","languages","text","contract","eligibility","planner","budget","runpod","tokens","guard","runstate","runlog","accounting","breaker"]:
    text = re.sub(rf"\btap_lms\.tapvoice\.{name}\b", f"tap_lms.tapvoice.lib.{name}", text)
for name in ["start","deploy","reaper","termination","reconcile","recover"]:
    text = re.sub(rf"\btap_lms\.tapvoice\.{name}\b", f"tap_lms.tapvoice.job.{name}", text)
for name in ["pod","operator"]:
    text = re.sub(rf"\btap_lms\.tapvoice\.{name}\b", f"tap_lms.tapvoice.api.{name}", text)
text = re.sub(r"\btap_lms\.tapvoice\.lib\.lib\b", "tap_lms.tapvoice.lib", text)
text = re.sub(r"\btap_lms\.tapvoice\.job\.job\b", "tap_lms.tapvoice.job", text)
text = re.sub(r"\btap_lms\.tapvoice\.api\.api\b", "tap_lms.tapvoice.api", text)
if text != original:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"patched {path}")
PYEOF
done

python3 - "$PKG/api/pod.py" << 'PYEOF'
import re, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    text = fh.read()
text = text.replace(
    "from tap_lms.tapvoice.lib.eligibility import SUBMISSION_DOCTYPE",
    "from tap_lms.tapvoice.lib.eligibility import SUBMISSION_DOCTYPE",
)
with open(path, "w", encoding="utf-8") as fh:
    fh.write(text)
PYEOF

python3 - "$REPO_ROOT" << 'PYEOF'
import pathlib, sys
root = pathlib.Path(sys.argv[1]) / "tap_lms" / "tapvoice"
for py in root.rglob("*.py"):
    text = py.read_text(encoding="utf-8")
    if "from tap_lms.tapvoice.lib.eligibility import SUBMISSION_DOCTYPE" in text and py.name == "eligibility.py":
        continue
    if py.parent.name == "lib" and "from tap_lms.tapvoice.lib." in text:
        text = text.replace("from tap_lms.tapvoice.lib.", "from tap_lms.tapvoice.lib.")
        py.write_text(text, encoding="utf-8")
PYEOF

grep -RIl "tap_lms\.tapvoice\.api\.pod\." "$REPO_ROOT/tap_lms/tap_lms/doctype" 2>/dev/null | while read -r file; do
  echo "verify whitelisted path reference: $file"
done

echo "done. next steps:"
echo "1. bench -site <site> migrate"
echo "2. bench -site <site> run-tests --app tap_lms --module tap_lms.tapvoice.test"
echo "3. grep -R 'tap_lms.tapvoice' tap_lms/tap_lms/doctype --include=*.js  (confirm client-side whitelisted calls still point at tap_lms.tapvoice.api.operator.* and tap_lms.tapvoice.api.pod.*)"