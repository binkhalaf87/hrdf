from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz

from matcher.arabic_utils import normalize_arabic, normalize_for_comparison
from matcher.transliteration import transliteration_similarity, normalize_english_name


@dataclass
class NameScore:
    score: float
    method: str


def _is_arabic(text: str) -> bool:
    """Return True if text contains Arabic characters."""
    return any("؀" <= ch <= "ۿ" for ch in text)


def exact_arabic_match(name_a: str, name_b: str) -> Optional[NameScore]:
    """
    Stage 3: exact match after Arabic normalization.
    """
    if not (_is_arabic(name_a) and _is_arabic(name_b)):
        return None

    norm_a = normalize_for_comparison(name_a)
    norm_b = normalize_for_comparison(name_b)

    if norm_a == norm_b:
        return NameScore(score=100.0, method="exact_arabic")
    return None


def fuzzy_arabic_match(name_a: str, name_b: str) -> Optional[NameScore]:
    """
    Stage 4: fuzzy matching on normalized Arabic names.
    Uses token_sort_ratio + WRatio to handle word reordering.
    """
    if not (_is_arabic(name_a) and _is_arabic(name_b)):
        return None

    norm_a = normalize_for_comparison(name_a)
    norm_b = normalize_for_comparison(name_b)

    score = max(
        fuzz.token_sort_ratio(norm_a, norm_b),
        fuzz.token_set_ratio(norm_a, norm_b),
        fuzz.WRatio(norm_a, norm_b),
    )
    return NameScore(score=float(score), method="fuzzy_arabic")


def transliteration_match(arabic_name: str, bank_name: str) -> Optional[NameScore]:
    """
    Stage 5: Arabic ↔ English transliteration matching.
    Handles cases where Hadaf has Arabic name and bank has English name.
    """
    if _is_arabic(arabic_name) and not _is_arabic(bank_name):
        score = transliteration_similarity(arabic_name, bank_name)
        return NameScore(score=score, method="transliteration_ar_en")

    if _is_arabic(bank_name) and not _is_arabic(arabic_name):
        score = transliteration_similarity(bank_name, arabic_name)
        return NameScore(score=score, method="transliteration_en_ar")

    # Both Arabic — try normalizing and comparing as English transliterations
    if _is_arabic(arabic_name) and _is_arabic(bank_name):
        score = transliteration_similarity(arabic_name, bank_name)
        return NameScore(score=score, method="transliteration_both_ar")

    return None


def best_name_score(hadaf_name: str, bank_name: str) -> NameScore:
    """
    Run all name-matching stages and return the best score.
    Stages run in order; exact match short-circuits.
    """
    # Stage 3: Exact Arabic
    result = exact_arabic_match(hadaf_name, bank_name)
    if result and result.score == 100.0:
        return result

    candidates: list[NameScore] = []

    # Stage 4: Fuzzy Arabic
    fuzzy = fuzzy_arabic_match(hadaf_name, bank_name)
    if fuzzy:
        candidates.append(fuzzy)

    # Stage 5: Transliteration
    trans = transliteration_match(hadaf_name, bank_name)
    if trans:
        candidates.append(trans)

    if not candidates:
        return NameScore(score=0.0, method="no_match")

    return max(candidates, key=lambda c: c.score)
