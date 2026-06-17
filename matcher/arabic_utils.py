from __future__ import annotations

import re
import unicodedata


# Arabic Unicode ranges and character maps
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۤۧۨ-ۭ]")
_TATWEEL = re.compile(r"ـ")

_ALEF_VARIANTS = str.maketrans("أإآٱ", "اااا")
_TEH_MARBUTA = str.maketrans("ة", "ه")
_YEH_VARIANTS = str.maketrans("ىئ", "يي")
_WAW_HAMZA = str.maketrans("ؤ", "و")
_HAMZA_VARIANTS = str.maketrans("ءأإآ", "ااا ")  # treat hamza as empty or alef

# Common name prefixes/tokens to normalize
_BIN_PATTERNS = re.compile(r"\bابن\b|\bاِبن\b", re.UNICODE)
_BIN_REPLACEMENT = "بن"

# عبدال__ with/without space
_ABD_AL_PATTERN = re.compile(r"عبد\s+ال(\w+)", re.UNICODE)
_ABD_AL_REPLACEMENT = r"عبدال\1"

# Remove common stop words that appear in names but vary
_AL_PREFIX_PATTERN = re.compile(r"\bال(\w+)", re.UNICODE)


def remove_diacritics(text: str) -> str:
    return _DIACRITICS.sub("", text)


def normalize_alef(text: str) -> str:
    return text.translate(_ALEF_VARIANTS)


def normalize_teh_marbuta(text: str) -> str:
    return text.translate(_TEH_MARBUTA)


def normalize_yeh(text: str) -> str:
    return text.translate(_YEH_VARIANTS)


def remove_tatweel(text: str) -> str:
    return _TATWEEL.sub("", text)


def normalize_bin(text: str) -> str:
    """Normalize ابن → بن."""
    return _BIN_PATTERNS.sub(_BIN_REPLACEMENT, text)


def normalize_abd_al(text: str) -> str:
    """عبد الرحمن → عبدالرحمن."""
    return _ABD_AL_PATTERN.sub(_ABD_AL_REPLACEMENT, text)


def strip_al_prefix(word: str) -> str:
    """Remove leading ال from a single word."""
    if word.startswith("ال") and len(word) > 2:
        return word[2:]
    return word


def normalize_arabic(text: str) -> str:
    """
    Full Arabic text normalization pipeline.

    Steps:
    1. Remove diacritics (tashkeel)
    2. Remove tatweel
    3. Normalize alef variants → ا
    4. Normalize teh marbuta → ه
    5. Normalize yeh variants → ي
    6. Normalize بن/ابن → بن
    7. Normalize عبد ال → عبدال
    8. Collapse whitespace
    """
    text = remove_diacritics(text)
    text = remove_tatweel(text)
    text = normalize_alef(text)
    text = normalize_teh_marbuta(text)
    text = normalize_yeh(text)
    text = normalize_bin(text)
    text = normalize_abd_al(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_for_comparison(text: str) -> str:
    """
    Extended normalization for comparison purposes:
    also strips ال prefix from each word.
    """
    normalized = normalize_arabic(text)
    words = [strip_al_prefix(w) for w in normalized.split()]
    return " ".join(words)


def tokenize_arabic_name(name: str) -> list[str]:
    """Split a normalized Arabic name into tokens, removing ال prefixes."""
    normalized = normalize_for_comparison(name)
    return [w for w in normalized.split() if len(w) > 1]
