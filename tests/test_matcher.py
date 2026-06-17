"""Unit tests for the matching engine and Arabic utilities."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from matcher.arabic_utils import (
    normalize_arabic,
    normalize_for_comparison,
    normalize_bin,
    normalize_abd_al,
    remove_diacritics,
)
from matcher.transliteration import (
    transliterate_arabic_to_english,
    normalize_english_name,
    transliteration_similarity,
)
from matcher.name_matcher import best_name_score, exact_arabic_match
from matcher.matching_engine import MatchingEngine
from models import BankEmployee, HadafEmployee


# ---------------------------------------------------------------------------
# Arabic Utils Tests
# ---------------------------------------------------------------------------

class TestArabicNormalization:
    def test_removes_diacritics(self):
        assert remove_diacritics("مُحَمَّد") == "محمد"

    def test_normalizes_alef_variants(self):
        result = normalize_arabic("أحمد إبراهيم آدم")
        assert "أ" not in result
        assert "إ" not in result
        assert "آ" not in result

    def test_normalizes_teh_marbuta(self):
        result = normalize_arabic("فاطمة")
        assert "ة" not in result
        assert "ه" in result

    def test_normalizes_ibn_to_bin(self):
        result = normalize_bin("عبدالله ابن خالد")
        assert "بن" in result
        assert "ابن" not in result

    def test_normalizes_abd_al_spacing(self):
        result = normalize_abd_al("عبد الرحمن")
        assert result == "عبدالرحمن"

    def test_full_normalization_pipeline(self):
        name1 = normalize_for_comparison("عَبدالرَّحمَن الرَّشيدي")
        name2 = normalize_for_comparison("عبدالرحمن الرشيدي")
        assert name1 == name2

    def test_al_prefix_stripped_in_comparison(self):
        name1 = normalize_for_comparison("الرشيدي")
        name2 = normalize_for_comparison("رشيدي")
        assert name1 == name2


# ---------------------------------------------------------------------------
# Transliteration Tests
# ---------------------------------------------------------------------------

class TestTransliteration:
    def test_basic_transliteration(self):
        result = transliterate_arabic_to_english("محمد")
        assert "M" in result

    def test_abd_pattern(self):
        result = transliterate_arabic_to_english("عبدالرحمن")
        assert result == "ABDULRAHMAN"

    def test_transliteration_similarity_high(self):
        score = transliteration_similarity("عساف عبدالرحمن الرشيدي", "ASSAF ABDULRAHMAN ALRASHIDI")
        assert score >= 75.0, f"Expected >= 75, got {score}"

    def test_normalize_english_name(self):
        result = normalize_english_name("  mohammed  ahmed  ")
        assert result == "MOHAMMED AHMED"

    def test_ben_to_bin_normalization(self):
        result = normalize_english_name("SAAD BEN SALMAN")
        assert "BIN" in result


# ---------------------------------------------------------------------------
# Name Matcher Tests
# ---------------------------------------------------------------------------

class TestNameMatcher:
    def test_exact_arabic_match(self):
        result = exact_arabic_match("عبدالله خالد", "عبدالله خالد")
        assert result is not None
        assert result.score == 100.0

    def test_exact_arabic_match_with_normalization(self):
        result = exact_arabic_match("عبد الرحمن", "عبدالرحمن")
        assert result is not None
        assert result.score == 100.0

    def test_arabic_english_fuzzy_match(self):
        score_result = best_name_score("عساف عبدالرحمن الرشيدي", "ASSAF ABDULRAHMAN ALRASHIDI")
        assert score_result.score >= 75.0

    def test_fuzzy_arabic_match(self):
        score_result = best_name_score("محمد احمد الزهراني", "محمد أحمد الزهراني")
        assert score_result.score >= 90.0

    def test_no_match(self):
        score_result = best_name_score("علي محمد", "JOHN SMITH")
        assert score_result.score < 50.0


# ---------------------------------------------------------------------------
# Matching Engine Tests
# ---------------------------------------------------------------------------

class TestMatchingEngine:
    def _make_hadaf(self) -> list[HadafEmployee]:
        return [
            HadafEmployee(1, "عساف عبدالرحمن الرشيدي", national_id="1234567890"),
            HadafEmployee(2, "محمد أحمد الزهراني", national_id="1098765432"),
            HadafEmployee(3, "خالد عبدالله السبيعي"),
        ]

    def _make_bank(self) -> list[BankEmployee]:
        return [
            BankEmployee(
                name="ASSAF ABDULRAHMAN ALRASHIDI",
                iban="SA1234567890123456789012",
                amount=6121.0,
                national_id="1234567890",
            ),
            BankEmployee(
                name="MOHAMMED AHMED ALZAHRANI",
                iban="SA0987654321098765432109",
                amount=6500.0,
                national_id="1098765432",
            ),
            BankEmployee(
                name="خالد عبدالله السبيعي",
                iban="SA1122334455112233445511",
                amount=7200.0,
            ),
            BankEmployee(
                name="UNKNOWN EMPLOYEE",
                iban="SA9999999999999999999999",
                amount=1000.0,
            ),
        ]

    def test_nid_stage_matches(self):
        engine = MatchingEngine()
        hadaf = [HadafEmployee(1, "عساف الرشيدي", national_id="1234567890")]
        bank = [BankEmployee("ASSAF", national_id="1234567890", amount=1000)]
        result = engine.match(hadaf, bank)
        assert len(result.matched) == 1
        assert result.matched[0].match_method == "national_id"

    def test_full_match_scenario(self):
        engine = MatchingEngine()
        hadaf = self._make_hadaf()
        bank = self._make_bank()
        result = engine.match(hadaf, bank)

        total_processed = len(result.matched) + len(result.review) + len(result.unmatched_bank)
        assert total_processed == len(bank)

    def test_summary_counts_correct(self):
        engine = MatchingEngine()
        hadaf = self._make_hadaf()
        bank = self._make_bank()
        result = engine.match(hadaf, bank)

        assert result.summary.total_hadaf == 3
        assert result.summary.total_bank == 4
        assert (
            result.summary.matched
            + result.summary.review_required
            + result.summary.unmatched
            == 4
        )

    def test_unmatched_employee_identified(self):
        engine = MatchingEngine()
        hadaf = self._make_hadaf()
        bank = self._make_bank()
        result = engine.match(hadaf, bank)

        unmatched_names = [e.name for e in result.unmatched_bank]
        assert "UNKNOWN EMPLOYEE" in unmatched_names

    def test_success_rate_calculation(self):
        engine = MatchingEngine()
        hadaf = [HadafEmployee(1, "محمد احمد", national_id="1111111111")]
        bank = [
            BankEmployee("MOHAMMED AHMED", national_id="1111111111", amount=5000),
            BankEmployee("UNKNOWN PERSON", amount=3000),
        ]
        result = engine.match(hadaf, bank)
        # 1 matched out of 2 bank records = 50%
        assert result.summary.total_bank == 2
        assert result.summary.matched == 1


# ---------------------------------------------------------------------------
# Processing Summary Tests
# ---------------------------------------------------------------------------

class TestProcessingSummary:
    def test_success_rate_zero_division(self):
        from models import ProcessingSummary
        s = ProcessingSummary(total_bank=0, matched=0)
        assert s.success_rate == 0.0

    def test_success_rate_calculation(self):
        from models import ProcessingSummary
        s = ProcessingSummary(total_bank=10, matched=8)
        assert s.success_rate == 80.0
