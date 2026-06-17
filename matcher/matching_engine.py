from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models import BankEmployee, BankReportRow, HadafEmployee, MatchResult, ProcessingSummary
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
    bank_report: list[BankReportRow]       # جميع سجلات البنك + بيانات هدف المطابقة
    summary: ProcessingSummary


def _determine_status(confidence: float) -> str:
    if confidence >= CONFIG.thresholds.HIGH_CONFIDENCE:
        return "matched"
    if confidence >= CONFIG.thresholds.REVIEW:
        return "review"
    return "unmatched"


def _amount_diff(bank: float, hadaf: Optional[float]) -> Optional[float]:
    if hadaf is None or bank == 0:
        return None
    return round(bank - hadaf, 2)


class MatchingEngine:
    """
    5-stage matching pipeline:
    Stage 1  — IBAN (Hadaf has IBAN)     → 100%
    Stage 2  — National ID               → 100%
    Stage 3  — Bank serial == Hadaf serial → 100%
    Stage 4  — Arabic name exact (normalised) → 100%
    Stage 5a — RapidFuzz fuzzy Arabic    → variable
    Stage 5b — Arabic↔English transliteration → variable
    """

    def match(
        self,
        hadaf_employees: list[HadafEmployee],
        bank_employees: list[BankEmployee],
    ) -> EngineResult:

        matched: list[MatchResult] = []
        review: list[MatchResult] = []
        unmatched_bank: list[BankEmployee] = []

        # Build lookup indices
        hadaf_by_iban: dict[str, HadafEmployee] = {
            e.iban.upper(): e for e in hadaf_employees if e.iban
        }
        hadaf_by_nid: dict[str, HadafEmployee] = {
            e.national_id: e for e in hadaf_employees if e.national_id
        }
        matched_hadaf_serials: set[int] = set()

        bank_report: list[BankReportRow] = []

        for bank_emp in bank_employees:
            result = self._match_single(
                bank_emp, hadaf_employees,
                hadaf_by_iban, hadaf_by_nid,
                matched_hadaf_serials,
            )

            if result and result.status != "unmatched":
                matched_hadaf_serials.add(result.hadaf_serial)
                if result.status == "matched":
                    matched.append(result)
                else:
                    review.append(result)

                bank_report.append(BankReportRow(
                    bank_name=result.bank_name,
                    hadaf_serial=result.hadaf_serial,
                    hadaf_name=result.hadaf_name,
                    iban=result.iban,
                    bank_amount=result.bank_amount,
                    hadaf_support_amount=result.hadaf_support_amount,
                    amount_diff=result.amount_diff,
                    match_method=result.match_method,
                    confidence=result.confidence,
                    status=result.status,
                    reference=bank_emp.reference,
                ))
            else:
                unmatched_bank.append(bank_emp)
                bank_report.append(BankReportRow(
                    bank_name=bank_emp.name,
                    hadaf_serial=None,
                    hadaf_name=None,
                    iban=bank_emp.iban,
                    bank_amount=bank_emp.amount,
                    hadaf_support_amount=None,
                    amount_diff=None,
                    match_method=None,
                    confidence=None,
                    status="bank_only",
                    reference=bank_emp.reference,
                ))

        unmatched_hadaf = [
            e for e in hadaf_employees if e.serial not in matched_hadaf_serials
        ]

        summary = ProcessingSummary(
            total_hadaf=len(hadaf_employees),
            total_bank=len(bank_employees),
            matched=len(matched),
            review_required=len(review),
            unmatched=len(unmatched_bank),
            hadaf_not_in_bank=len(unmatched_hadaf),
        )

        logger.info(
            "Matching — matched=%d review=%d unmatched=%d hadaf_not_in_bank=%d",
            summary.matched, summary.review_required,
            summary.unmatched, summary.hadaf_not_in_bank,
        )

        return EngineResult(
            matched=matched,
            review=review,
            unmatched_bank=unmatched_bank,
            unmatched_hadaf=unmatched_hadaf,
            bank_report=bank_report,
            summary=summary,
        )

    def _match_single(
        self,
        bank_emp: BankEmployee,
        hadaf_employees: list[HadafEmployee],
        hadaf_by_iban: dict[str, HadafEmployee],
        hadaf_by_nid: dict[str, HadafEmployee],
        already_matched: set[int],
    ) -> Optional[MatchResult]:

        # --- Stage 1: IBAN match (highest priority) ---
        if bank_emp.iban:
            hadaf = hadaf_by_iban.get(bank_emp.iban.upper())
            if hadaf and hadaf.serial not in already_matched:
                logger.debug("Stage 1 (IBAN): %s", hadaf.name_arabic)
                return self._build(hadaf, bank_emp, "iban", 100.0)

        # --- Stage 2: National ID match ---
        if bank_emp.national_id:
            hadaf = hadaf_by_nid.get(bank_emp.national_id)
            if hadaf and hadaf.serial not in already_matched:
                logger.debug("Stage 2 (NID): %s", hadaf.name_arabic)
                return self._build(hadaf, bank_emp, "national_id", 100.0)

        # --- Stage 3: Serial number match ---
        if bank_emp.serial is not None:
            for hadaf in hadaf_employees:
                if hadaf.serial == bank_emp.serial and hadaf.serial not in already_matched:
                    logger.debug("Stage 3 (serial): %s", hadaf.name_arabic)
                    return self._build(hadaf, bank_emp, "serial_number", 100.0)

        # --- Stages 4-5: Name-based matching ---
        best_hadaf: Optional[HadafEmployee] = None
        best_score: float = 0.0
        best_method: str = "no_match"

        for hadaf in hadaf_employees:
            if hadaf.serial in already_matched:
                continue
            ns = best_name_score(hadaf.name_arabic, bank_emp.name)
            if ns.score > best_score:
                best_score = ns.score
                best_hadaf = hadaf
                best_method = ns.method

        if best_hadaf is None or best_score < CONFIG.thresholds.REVIEW:
            return None

        logger.debug("Stage name (%s %.1f%%): %s ↔ %s",
                     best_method, best_score, best_hadaf.name_arabic, bank_emp.name)
        return self._build(best_hadaf, bank_emp, best_method, best_score)

    @staticmethod
    def _build(
        hadaf: HadafEmployee,
        bank: BankEmployee,
        method: str,
        confidence: float,
    ) -> MatchResult:
        diff = _amount_diff(bank.amount, hadaf.support_amount)
        return MatchResult(
            hadaf_serial=hadaf.serial,
            hadaf_name=hadaf.name_arabic,
            bank_name=bank.name,
            bank_amount=bank.amount,
            iban=bank.iban or hadaf.iban,
            match_method=method,
            confidence=round(confidence, 2),
            status=_determine_status(confidence),
            hadaf_support_amount=hadaf.support_amount,
            amount_diff=diff,
        )
