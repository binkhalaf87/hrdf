from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models import BankEmployee, HadafEmployee, MatchResult, ProcessingSummary
from matcher.name_matcher import best_name_score
from utils.config import CONFIG
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EngineResult:
    matched: list[MatchResult]
    review: list[MatchResult]
    unmatched_bank: list[BankEmployee]
    unmatched_hadaf: list[HadafEmployee]
    summary: ProcessingSummary


def _determine_status(confidence: float) -> str:
    if confidence >= CONFIG.thresholds.HIGH_CONFIDENCE:
        return "matched"
    if confidence >= CONFIG.thresholds.REVIEW:
        return "review"
    return "unmatched"


class MatchingEngine:
    """
    Orchestrates the 5-stage matching pipeline between Hadaf and Bank records.

    Stage 1: National ID (exact)
    Stage 2: IBAN (exact)
    Stage 3: Arabic name exact match (after normalization)
    Stage 4: RapidFuzz fuzzy matching on Arabic names
    Stage 5: Arabic ↔ English transliteration matching
    """

    def match(
        self,
        hadaf_employees: list[HadafEmployee],
        bank_employees: list[BankEmployee],
    ) -> EngineResult:
        matched: list[MatchResult] = []
        review: list[MatchResult] = []
        unmatched_bank: list[BankEmployee] = []
        unmatched_hadaf: list[HadafEmployee] = list(hadaf_employees)

        hadaf_by_nid: dict[str, HadafEmployee] = {
            e.national_id: e for e in hadaf_employees if e.national_id
        }
        hadaf_by_serial: dict[int, HadafEmployee] = {
            e.serial: e for e in hadaf_employees
        }
        matched_hadaf_serials: set[int] = set()

        for bank_emp in bank_employees:
            result = self._match_single(
                bank_emp, hadaf_employees, hadaf_by_nid, matched_hadaf_serials
            )
            if result:
                matched_hadaf_serials.add(result.hadaf_serial)
                if result.status == "matched":
                    matched.append(result)
                elif result.status == "review":
                    review.append(result)
                else:
                    unmatched_bank.append(bank_emp)
            else:
                unmatched_bank.append(bank_emp)

        # Hadaf employees with no bank counterpart
        unmatched_hadaf = [
            e for e in hadaf_employees if e.serial not in matched_hadaf_serials
        ]

        summary = ProcessingSummary(
            total_hadaf=len(hadaf_employees),
            total_bank=len(bank_employees),
            matched=len(matched),
            review_required=len(review),
            unmatched=len(unmatched_bank),
        )

        logger.info(
            "Matching complete — matched=%d review=%d unmatched=%d",
            summary.matched,
            summary.review_required,
            summary.unmatched,
        )
        return EngineResult(
            matched=matched,
            review=review,
            unmatched_bank=unmatched_bank,
            unmatched_hadaf=unmatched_hadaf,
            summary=summary,
        )

    def _match_single(
        self,
        bank_emp: BankEmployee,
        hadaf_employees: list[HadafEmployee],
        hadaf_by_nid: dict[str, HadafEmployee],
        already_matched: set[int],
    ) -> Optional[MatchResult]:

        # --- Stage 1: National ID ---
        if bank_emp.national_id and bank_emp.national_id in hadaf_by_nid:
            hadaf = hadaf_by_nid[bank_emp.national_id]
            if hadaf.serial not in already_matched:
                logger.debug("Stage 1 match (NID): %s", hadaf.name_arabic)
                return self._build_result(hadaf, bank_emp, "national_id", 100.0)

        # --- Stage 2: IBAN (if bank has IBAN and Hadaf records have IBAN) ---
        # Hadaf records rarely contain IBAN; if bank serial matches hadaf serial, use it
        if bank_emp.serial is not None:
            hadaf = self._find_by_serial(bank_emp.serial, hadaf_employees, already_matched)
            if hadaf:
                logger.debug("Stage 2-like match (serial): %s", hadaf.name_arabic)
                return self._build_result(hadaf, bank_emp, "serial_number", 100.0)

        # --- Stages 3–5: Name-based matching ---
        best_hadaf: Optional[HadafEmployee] = None
        best_score: float = 0.0
        best_method: str = "no_match"

        for hadaf in hadaf_employees:
            if hadaf.serial in already_matched:
                continue
            name_score = best_name_score(hadaf.name_arabic, bank_emp.name)
            if name_score.score > best_score:
                best_score = name_score.score
                best_hadaf = hadaf
                best_method = name_score.method

        if best_hadaf is None or best_score < CONFIG.thresholds.REVIEW:
            return None

        logger.debug(
            "Stage name match (%s, %.1f%%): %s → %s",
            best_method,
            best_score,
            best_hadaf.name_arabic,
            bank_emp.name,
        )
        return self._build_result(best_hadaf, bank_emp, best_method, best_score)

    @staticmethod
    def _find_by_serial(
        serial: int,
        employees: list[HadafEmployee],
        already_matched: set[int],
    ) -> Optional[HadafEmployee]:
        for emp in employees:
            if emp.serial == serial and emp.serial not in already_matched:
                return emp
        return None

    @staticmethod
    def _build_result(
        hadaf: HadafEmployee,
        bank: BankEmployee,
        method: str,
        confidence: float,
    ) -> MatchResult:
        status = _determine_status(confidence)
        return MatchResult(
            hadaf_serial=hadaf.serial,
            hadaf_name=hadaf.name_arabic,
            bank_name=bank.name,
            amount=bank.amount,
            iban=bank.iban,
            match_method=method,
            confidence=round(confidence, 2),
            status=status,
        )
