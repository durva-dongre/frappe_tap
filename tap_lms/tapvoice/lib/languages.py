LANGUAGE_VOICES = {
    "english": "English (Female)",
    "hindi": "Hindi (Female)",
    "marathi": "Marathi (Female)",
    "kannada": "Kannada (Female)",
    "punjabi": "Punjabi (Female)",
}

LANGUAGE_ALIASES = {
    "en": "english",
    "hi": "hindi",
    "mr": "marathi",
    "kn": "kannada",
    "pa": "punjabi",
    "english": "english",
    "hindi": "hindi",
    "marathi": "marathi",
    "kannada": "kannada",
    "punjabi": "punjabi",
}


def normalize(value):
    if not isinstance(value, str):
        return None
    return LANGUAGE_ALIASES.get(value.strip().lower())


def voice_for(language):
    return LANGUAGE_VOICES.get(language)