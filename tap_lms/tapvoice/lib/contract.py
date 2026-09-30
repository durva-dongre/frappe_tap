import hashlib

from tap_lms.tapvoice.lib.languages import voice_for
from tap_lms.tapvoice.lib.text import clean_text


def content_hash(text, voice, emotion, fmt, model_revision):
    parts = [
        clean_text(text),
        voice,
        emotion or "",
        fmt,
        model_revision,
    ]
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def expected_hash(text, language, model_revision, fmt="ogg"):
    voice = voice_for(language)
    return content_hash(text, voice, None, fmt, model_revision)


def object_key(prefix, language, digest, fmt="ogg"):
    return f"{prefix}/{language}/{digest[:32]}.{fmt}"


def expected_key(text, voice, emotion, fmt, model_revision, prefix, language):
    digest = content_hash(text, voice, emotion, fmt, model_revision)
    return object_key(prefix, language, digest, fmt)


def expected_url(text, language, model_revision, gcs_prefix, cdn_base_url, fmt="ogg"):
    digest = expected_hash(text, language, model_revision, fmt)
    key = object_key(gcs_prefix, language, digest, fmt)
    return f"{cdn_base_url}/{key}"


def hash_matches(reported_hash, expected):
    if not reported_hash or not expected:
        return False
    return reported_hash == expected


def url_matches(reported_url, expected):
    if not reported_url or not expected:
        return False
    return reported_url == expected