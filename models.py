from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HadafEmployee:
    serial: int
    name_arabic: str
    national_id: Optional[str] = None
    iban: Optional[str] = None           # مضاف — للمطابقة الدقيقة بالآيبان
    support_amount: Optional[float] = None  # قيمة الدعم في هدف (للمقارنة)


@dataclass
class BankEmployee:
    name: str
    iban: Optional[str] = None
    amount: float = 0.0
    reference: Optional[str] = None
    serial: Optional[int] = None
    national_id: Optional[str] = None


@dataclass
class MatchResult:
    hadaf_serial: int
    hadaf_name: str
    bank_name: str
    bank_amount: float
    iban: Optional[str]
    match_method: str
    confidence: float
    status: str                          # 'matched' | 'review' | 'unmatched'
    hadaf_support_amount: Optional[float] = None
    amount_diff: Optional[float] = None  # bank_amount - hadaf_support_amount


@dataclass
class BankReportRow:
    """صف في تقرير البنك المُحدَّث — يضاف الرقم التسلسلي لهدف لكل موظف مطابق."""
    bank_name: str
    hadaf_serial: Optional[int]
    hadaf_name: Optional[str]
    iban: Optional[str]
    bank_amount: float
    hadaf_support_amount: Optional[float]
    amount_diff: Optional[float]
    match_method: Optional[str]
    confidence: Optional[float]
    status: str                          # 'matched' | 'review' | 'bank_only'
    reference: Optional[str] = None


@dataclass
class ProcessingSummary:
    total_hadaf: int = 0
    total_bank: int = 0
    matched: int = 0
    review_required: int = 0
    unmatched: int = 0
    hadaf_not_in_bank: int = 0          # موظفو هدف لم ينزل راتبهم

    @property
    def success_rate(self) -> float:
        if self.total_bank == 0:
            return 0.0
        return round(((self.matched) / self.total_bank) * 100, 2)
