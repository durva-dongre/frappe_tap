import frappe

TEST_MODEL_REVISION = "test-rev"


def _settings_with_revision(revision=TEST_MODEL_REVISION):
    return frappe._dict(
        model_revision=revision,
        gcs_prefix="tts",
        cdn_base_url="https://cdn.example.com",
        max_text_chars=300,
        verify_urls_on_write=0,
    )