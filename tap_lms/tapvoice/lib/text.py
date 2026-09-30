import hashlib
import re
import unicodedata

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


def prepare(raw_text, language, max_chars, policy):
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


def fingerprint(prepared_text, language):
    payload = f"{prepared_text}\x1f{language}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()