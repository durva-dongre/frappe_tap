#!/bin/sh

set -e

BASE="tap_lms/tap_lms/doctype"

if [ ! -d "$BASE" ]; then
    echo "error: $BASE not found relative to current directory ($(pwd))." >&2
    echo "Run this script from /workspaces/frappe_tap/, or edit BASE at the top of this script." >&2
    exit 1
fi

USE_GIT=0
if [ -d ".git" ] && command -v git >/dev/null 2>&1; then
    USE_GIT=1
fi

mv_path() {
    old="$1"
    new="$2"
    if [ ! -e "$old" ]; then
        return 0
    fi
    if [ "$USE_GIT" = "1" ]; then
        git mv "$old" "$new"
    else
        mv "$old" "$new"
    fi
    echo "renamed: $old -> $new"
}

rename_settings() {
    old_dir="$BASE/tapvoice_settings"
    new_dir="$BASE/tap_voice_settings"

    if [ ! -d "$old_dir" ]; then
        echo "skip: $old_dir does not exist"
        return 0
    fi

    mv_path "$old_dir" "$new_dir"

    mv_path "$new_dir/tapvoice_settings.json" "$new_dir/tap_voice_settings.json"
    mv_path "$new_dir/tapvoice_settings.py"   "$new_dir/tap_voice_settings.py"
    mv_path "$new_dir/tapvoice_settings.js"   "$new_dir/tap_voice_settings.js"
}

rename_run() {
    old_dir="$BASE/tapvoice_run"
    new_dir="$BASE/tap_voice_run"

    if [ ! -d "$old_dir" ]; then
        echo "skip: $old_dir does not exist"
        return 0
    fi

    mv_path "$old_dir" "$new_dir"

    mv_path "$new_dir/tapvoice_run.json"      "$new_dir/tap_voice_run.json"
    mv_path "$new_dir/tapvoice_run.py"        "$new_dir/tap_voice_run.py"
    mv_path "$new_dir/tapvoice_run.js"        "$new_dir/tap_voice_run.js"
    mv_path "$new_dir/tapvoice_run_list.js"   "$new_dir/tap_voice_run_list.js"
    mv_path "$new_dir/test_tapvoice_run.py"   "$new_dir/test_tap_voice_run.py"
}

rename_settings
rename_run

echo ""
echo "done. If this repo is checked out inside a frappe-bench apps folder, next run:"
echo "  bench --site <your-site> clear-cache"
echo "  bench --site <your-site> migrate"