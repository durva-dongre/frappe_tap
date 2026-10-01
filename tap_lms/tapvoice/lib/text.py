import hashlib
import re
import unicodedata
from collections import namedtuple

from tap_lms.tapvoice.lib import languages

_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")
_MARKDOWN_RE = re.compile(r"[*_`#>~]")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]",
    flags=re.UNICODE,
)
_SENTENCE_END_RE = re.compile(r"[.!?\u0964]")

PreparedText = namedtuple("PreparedText", "text language fingerprint truncated")


def strip_markup(text):
    without_tags = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", without_tags).strip()


def _strip_markdown_and_emoji(text):
    without_markdown = _MARKDOWN_RE.sub("", text)
    without_emoji = _EMOJI_RE.sub("", without_markdown)
    return without_emoji


def clean_text(text):
    normalized = unicodedata.normalize("NFC", text)
    out = []
    for ch in normalized:
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf", "Cs", "Co", "Cn") and ch not in ("\n", "\t"):
            continue
        out.append(ch)
    collapsed = "".join(out).replace("\t", " ").replace("\n", " ")
    return " ".join(collapsed.split())


def _truncate(text, limit):
    if len(text) <= limit:
        return text, False
    window = text[:limit]
    matches = list(_SENTENCE_END_RE.finditer(window))
    if matches:
        cut = matches[-1].end()
        return window[:cut].strip(), True
    last_space = window.rfind(" ")
    if last_space > 0:
        return window[:last_space].strip(), True
    return "", True


def prepare(raw_text, max_chars, policy):
    stripped_tags = strip_markup(raw_text)
    stripped = _strip_markdown_and_emoji(stripped_tags)
    cleaned = clean_text(stripped)
    if len(cleaned) <= max_chars:
        return cleaned, False
    if policy == "skip":
        return "", True
    truncated, was_truncated = _truncate(cleaned, max_chars)
    reclaimed = clean_text(truncated)
    return reclaimed, was_truncated


def fingerprint(text, language):
    payload = f"{language}\x1f{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def prepare_item(raw_text, raw_language, max_chars, policy):
    language = languages.normalize(raw_language)
    if language is None:
        return None
    cleaned, truncated = prepare(raw_text or "", max_chars, policy)
    if not cleaned:
        return None
    return PreparedText(cleaned, language, fingerprint(cleaned, language), truncated)