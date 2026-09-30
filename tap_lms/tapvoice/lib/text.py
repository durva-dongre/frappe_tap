import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from tap_lms.tapvoice.lib.languages import normalize as normalize_language

HTML_TAG_RE = re.compile(r"<[^>]*>")
MARKDOWN_SYMBOL_RE = re.compile(r"[*_`#~>\[\]]")
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "]+",
    flags=re.UNICODE,
)
SENTENCE_END_RE = re.compile(r"[.!?\u0964\u0965]")


@dataclass(frozen=True)
class PreparedText:
    text: str
    language: str
    truncated: bool
    fingerprint: str


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


def strip_markup(text):
    without_tags = HTML_TAG_RE.sub(" ", text)
    without_emoji = EMOJI_RE.sub("", without_tags)
    without_markdown = MARKDOWN_SYMBOL_RE.sub("", without_emoji)
    return without_markdown


def truncate_at_boundary(text, max_chars):
    if len(text) <= max_chars:
        return text, False
    window = text[:max_chars]
    best = -1
    for match in SENTENCE_END_RE.finditer(window):
        best = match.end()
    if best > 0:
        return window[:best].strip(), True
    last_space = window.rfind(" ")
    if last_space > 0:
        return window[:last_space].strip(), True
    return window.strip(), True


def fingerprint_of(text, language):
    payload = f"{text}\x1f{language}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def prepare(raw_text, raw_language, max_chars, over_length_policy) -> Optional[PreparedText]:
    language = normalize_language(raw_language)
    if language is None:
        return None
    stripped = strip_markup(raw_text or "")
    cleaned = clean_text(stripped)
    if not cleaned:
        return None
    if len(cleaned) <= max_chars:
        final_text = cleaned
        truncated = False
    elif over_length_policy == "skip":
        return None
    else:
        truncated_text, truncated = truncate_at_boundary(cleaned, max_chars)
        final_text = clean_text(truncated_text)
        if not final_text:
            return None
    reclean = clean_text(final_text)
    if reclean != final_text:
        final_text = reclean
    fingerprint = fingerprint_of(final_text, language)
    return PreparedText(text=final_text, language=language, truncated=truncated, fingerprint=fingerprint)