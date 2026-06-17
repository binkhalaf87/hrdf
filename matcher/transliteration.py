from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Arabic → English character-level transliteration table
# Based on Saudi passport/ID transliteration conventions
# ---------------------------------------------------------------------------
_CHAR_MAP: dict[str, str] = {
    "ا": "A",
    "أ": "A",
    "إ": "A",
    "آ": "AA",
    "ب": "B",
    "ت": "T",
    "ث": "TH",
    "ج": "J",
    "ح": "H",
    "خ": "KH",
    "د": "D",
    "ذ": "TH",
    "ر": "R",
    "ز": "Z",
    "س": "S",
    "ش": "SH",
    "ص": "S",
    "ض": "D",
    "ط": "T",
    "ظ": "TH",
    "ع": "A",
    "غ": "GH",
    "ف": "F",
    "ق": "Q",
    "ك": "K",
    "ل": "L",
    "م": "M",
    "ن": "N",
    "ه": "H",
    "ة": "H",
    "و": "W",
    "ي": "Y",
    "ى": "A",
    "ء": "",
    "ئ": "Y",
    "ؤ": "W",
    "لا": "LA",  # lam-alef ligature
}

# Word-level prefix/token replacements (applied before char transliteration)
_WORD_MAP: dict[str, str] = {
    "ال": "AL",
    "بن": "BIN",
    "ابن": "BIN",
    "بنت": "BINT",
    "أبو": "ABU",
    "ابو": "ABU",
    "أم": "UM",
    "ام": "UM",
    "عبد": "ABD",
    "عبدالرحمن": "ABDULRAHMAN",
    "عبدالله": "ABDULLAH",
    "عبدالعزيز": "ABDULAZIZ",
    "عبدالرحيم": "ABDULRAHIM",
    "عبدالكريم": "ABDULKARIM",
    "عبدالحميد": "ABDULHAMID",
    "عبدالمجيد": "ABDULMAJEED",
    "عبدالحكيم": "ABDULHAKIM",
    "عبدالواحد": "ABDULWAHID",
    "عبدالوهاب": "ABDULWAHAB",
    "عبدالمحسن": "ABDULMOHSEN",
    "عبدالسلام": "ABDULSALAM",
    "عبدالناصر": "ABDULNASSER",
    "عبدالرزاق": "ABDULRAZZAQ",
    "عبدالمنعم": "ABDULMUNEM",
    "عبدالستار": "ABDULSATTAR",
    "عبدالباري": "ABDULBARI",
    "عبدالقادر": "ABDULQADIR",
    "عبدالغفار": "ABDULGAFFAR",
    "عبدالرؤوف": "ABDULRAUF",
    "عبدالمالك": "ABDULMALIK",
    "عبدالفتاح": "ABDUFATTAH",
}

# Normalize common English name variants
_ENGLISH_NORMALIZATION: dict[str, str] = {
    "BEN": "BIN",
    "BINN": "BIN",
    "ALAHMAN": "ALRAHMAN",
    "ABDEL": "ABD",
    "ABDAL": "ABD",
    "ABDEL ": "ABDU",
}


def _transliterate_word(word: str) -> str:
    """Transliterate a single Arabic word to English."""
    if word in _WORD_MAP:
        return _WORD_MAP[word]

    result = []
    i = 0
    while i < len(word):
        # Try two-char match first (لا ligature, etc.)
        two_char = word[i : i + 2]
        if two_char in _CHAR_MAP:
            result.append(_CHAR_MAP[two_char])
            i += 2
        elif word[i] in _CHAR_MAP:
            result.append(_CHAR_MAP[word[i]])
            i += 1
        else:
            i += 1  # skip unknown chars (tashkeel already removed upstream)

    return "".join(result)


def transliterate_arabic_to_english(arabic_name: str) -> str:
    """
    Convert an Arabic name to its English transliteration.

    Example:
        عساف عبدالرحمن الرشيدي → ASSAF ABDULRAHMAN ALRASHIDI
    """
    # Remove diacritics first (import-free inline)
    cleaned = re.sub(r"[ً-ٰٟ]", "", arabic_name)
    words = cleaned.split()
    transliterated = [_transliterate_word(w) for w in words if w]
    return " ".join(t for t in transliterated if t)


def normalize_english_name(name: str) -> str:
    """
    Normalize an English name for comparison:
    uppercase, collapse spaces, standardize BEN→BIN, etc.
    """
    normalized = name.upper().strip()
    normalized = re.sub(r"\s+", " ", normalized)

    for variant, canonical in _ENGLISH_NORMALIZATION.items():
        normalized = normalized.replace(variant, canonical)

    return normalized


def english_name_tokens(name: str) -> set[str]:
    """Return significant tokens from an English name (≥2 chars, no AL-)."""
    normalized = normalize_english_name(name)
    tokens = normalized.split()
    # Remove very short tokens like "AL" prefix when it's a standalone word
    return {t for t in tokens if len(t) >= 2}


def transliteration_similarity(arabic_name: str, english_name: str) -> float:
    """
    Compute similarity between an Arabic name (transliterated) and an English name.
    Returns 0.0 – 100.0.
    """
    from rapidfuzz import fuzz

    transliterated = transliterate_arabic_to_english(arabic_name)
    eng_normalized = normalize_english_name(english_name)

    # Multiple strategies — take the best score
    scores = [
        fuzz.token_sort_ratio(transliterated, eng_normalized),
        fuzz.token_set_ratio(transliterated, eng_normalized),
        fuzz.WRatio(transliterated, eng_normalized),
    ]
    return max(scores)
