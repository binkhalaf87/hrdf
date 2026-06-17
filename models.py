from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HadafEmployee:
    serial: int
    name_arabic: str
    national_id: Optional[str] = None
    support_data: Optional[str] = None


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
    amount: float
    iban: Optional[str]
    match_method: str
    confidence: float
    status: str  # 'matched' | 'review' | 'unmatched'


@dataclass
class ProcessingSummary:
    total_hadaf: int = 0
    total_bank: int = 0
    matched: int = 0
    review_required: int = 0
    unmatched: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_bank == 0:
            return 0.0
        return round((self.matched / self.total_bank) * 100, 2)
