"""
shared/export/event_exporter.py

Per-event JSON export to R2 + the aggregate events.json index. Scoped
narrowly -- this gives the two entry points hooks.py needs (so the
Event Campaign doc_event hook has somewhere to point) with a real, minimal
implementation rather than a stub, since event publish/unpublish needs
*something* to run without erroring.

Note: the general content-export pipeline (shared/export/content_exporter.py)
is being written separately; this file is the event-specific slice only and
is deliberately kept independent of it.
"""

from __future__ import annotations

import json

import frappe


def export_event_to_r2(event_campaign_name: str) -> None:
    """
    Builds a small JSON blob for one event (name, unit, pop-up text,
    translations) and PUTs it to R2 at events/{name}.json. Uses the same
    r2 credentials as submission promotion (Shared Settings.r2_*).
    Left as a narrow, working implementation; the full fallback-cascade /
    cache-tuning behavior described for gallery does NOT apply here, since
    events.json is a flat, infrequently-changing index, not a scoped query.
    """
    event = frappe.get_doc("Event Campaign", event_campaign_name)
    blob = {
        "event_id": event.name,
        "event_name": event.event_name,
        "learning_unit": event.learning_unit,
        "pop_up_text": event.pop_up_text,
        "status": event.status,
        "start_date": str(event.start_date),
        "end_date": str(event.end_date),
        "translations": [
            {
                "language": t.language,
                "event_name": t.translated_event_name,
                "pop_up_text": t.translated_pop_up_text,
            }
            for t in (event.event_translations or [])
        ],
    }
    _put_r2_json(f"events/{event.name}.json", blob)


def rebuild_events_index() -> None:
    """Rebuilds the flat events.json index of every public-facing event."""
    events = frappe.get_all(
        "Event Campaign",
        filters={"status": ["in", ("Published", "On going", "Completed")]},
        fields=["name", "event_name", "status", "start_date", "end_date",
                "region_scope", "region_list"],
    )
    _put_r2_json("events.json", {"events": events})


def on_event_campaign_update(doc, method=None) -> None:
    """doc_events hook target (tap_lms/hooks.py) for Event Campaign."""
    if doc.status in ("Published", "On going", "Completed"):
        export_event_to_r2(doc.name)
        rebuild_events_index()


def _put_r2_json(key: str, data: dict) -> None:
    from shared.config.secrets_cache import get_r2_credentials
    import boto3

    creds = get_r2_credentials()
    if not creds.get("account_id"):
        frappe.logger().warning(f"R2 not configured; skipping export of {key}")
        return
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{creds['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        region_name="auto",
    )
    client.put_object(
        Bucket=creds["bucket"], Key=key,
        Body=json.dumps(data, default=str).encode("utf-8"),
        ContentType="application/json",
    )