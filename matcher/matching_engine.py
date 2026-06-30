from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models import BankEmployee, BankReportRow, HadafEmployee, MatchResult, ProcessingSummary
from matcher.name_matcher import best_name_score
from utils.config import CONFIG
from utils.logger import get_logger

try:
    from matcher.claude_matcher import ClaudeIbanMatcher
    _claude_available = True
except ImportError:
    _claude_available = False

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
    Matching pipeline (IBAN is the only official match):
    Stage 1  — IBAN (Hadaf has IBAN)     → 100%
    Stage 2  — National ID               → 100% (مرجعي)
    Stage 3  — Bank serial == Hadaf serial → 100% (مرجعي)
    Stage 4-5 — Name-based               → variable (مرجعي)
    Stage 6  — Claude AI IBAN verification → يتحقق من آيبانات لم تتطابق نصياً
               (أخطاء OCR)، ويُعدّ تطابق آيبان رسمي. (اختياري، يتطلب مفتاح API)
    """

    def __init__(self, claude_api_key: Optional[str] = None):
        self._claude: Optional[ClaudeIbanMatcher] = None
        if claude_api_key and _claude_available:
            try:
                self._claude = ClaudeIbanMatcher(claude_api_key)
                logger.info("Claude AI IBAN verification enabled")
            except Exception as exc:
                logger.warning("Failed to init Claude matcher: %s", exc)

    def match(
        self,
        hadaf_employees: list[HadafEmployee],
        bank_employees: list[BankEmployee],
    ) -> EngineResult:

        matched: list[MatchResult] = []
        review: list[MatchResult] = []
        unmatched_bank: list[BankEmployee] = []

        # Build lookup indices — all 3 IBAN columns map to the same employee
        hadaf_by_iban: dict[str, HadafEmployee] = {}
        for e in hadaf_employees:
            for iban in e.all_ibans:
                hadaf_by_iban.setdefault(iban.upper(), e)
        hadaf_by_nid: dict[str, HadafEmployee] = {
            e.national_id: e for e in hadaf_employees if e.national_id
        }
        matched_hadaf_serials: set[int] = set()

        bank_report: list[BankReportRow] = []

        # Stage 1-5: run standard matching
        pending_unmatched: list[BankEmployee] = []

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
                pending_unmatched.append(bank_emp)

        # Stage 6: Claude AI matching for remaining unmatched employees
        if self._claude and pending_unmatched:
            pending_unmatched = self._run_claude_stage(
                pending_unmatched, hadaf_employees,
                matched_hadaf_serials, matched, review, bank_report,
            )

        for bank_emp in pending_unmatched:
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
    def _iban_char_diff(a: str, b: str) -> int:
        """عدد الخانات المختلفة بين آيبانين (إذا اختلف الطول → كبير)."""
        if len(a) != len(b):
            return 99
        return sum(1 for x, y in zip(a, b) if x != y)

    def _run_claude_stage(
        self,
        pending: list[BankEmployee],
        hadaf_employees: list[HadafEmployee],
        matched_hadaf_serials: set[int],
        matched: list[MatchResult],
        review: list[MatchResult],
        bank_report: list[BankReportRow],
    ) -> list[BankEmployee]:
        """
        تدقيق آيبانات بالذكاء الاصطناعي: الموظفون الذين عندهم آيبان في البنك
        لم يتطابق نصياً، نقارن آيبانهم مع آيبانات هدف القريبة (أخطاء OCR محتملة).
        التطابق المؤكد يُعدّ تطابق آيبان رسمي (claude_iban).
        """
        # آيبانات هدف المتاحة (لم تُطابَق بعد) مع الموظف صاحبها
        hadaf_ibans: list[tuple[str, HadafEmployee]] = []
        for e in hadaf_employees:
            if e.serial in matched_hadaf_serials:
                continue
            for iban in e.all_ibans:
                hadaf_ibans.append((iban.upper(), e))

        if not hadaf_ibans:
            return pending

        still_unmatched: list[BankEmployee] = []

        for bank_emp in pending:
            bank_iban = (bank_emp.iban or "").upper()
            if not bank_iban:
                still_unmatched.append(bank_emp)
                continue

            # رشّح آيبانات هدف القريبة (اختلاف ≤ 4 خانات) لتقليل تكلفة الـ API
            candidates = [
                (h_iban, emp) for h_iban, emp in hadaf_ibans
                if emp.serial not in matched_hadaf_serials
                and self._iban_char_diff(bank_iban, h_iban) <= 4
            ]
            if not candidates:
                still_unmatched.append(bank_emp)
                continue

            pairs = [(h_iban, bank_iban) for h_iban, _ in candidates]
            verdicts = self._claude.verify_pairs(pairs)  # type: ignore[union-attr]

            match_idx = next((i for i, ok in enumerate(verdicts) if ok), None)
            if match_idx is None:
                still_unmatched.append(bank_emp)
                continue

            best_hadaf = candidates[match_idx][1]
            result = self._build(best_hadaf, bank_emp, "claude_iban", 100.0)
            matched_hadaf_serials.add(best_hadaf.serial)
            logger.debug("Stage 6 (Claude IBAN): %s ↔ %s (هدف #%d)",
                         bank_iban, candidates[match_idx][0], best_hadaf.serial)

            matched.append(result)
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

        return still_unmatched

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
