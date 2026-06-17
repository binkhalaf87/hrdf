from dataclasses import dataclass


@dataclass(frozen=True)
class MatchThresholds:
    HIGH_CONFIDENCE: float = 95.0
    REVIEW: float = 80.0


@dataclass(frozen=True)
class OCRConfig:
    LANGUAGE: str = "ara+eng"
    TESSERACT_PSM: int = 6
    TESSERACT_OEM: int = 3
    DPI: int = 300

    @property
    def config_string(self) -> str:
        return f"--oem {self.TESSERACT_OEM} --psm {self.TESSERACT_PSM}"


@dataclass(frozen=True)
class AppConfig:
    thresholds: MatchThresholds = MatchThresholds()
    ocr: OCRConfig = OCRConfig()
    MIN_TEXT_CHARS_FOR_TEXT_PDF: int = 50
    MAX_FUZZY_CANDIDATES: int = 3


CONFIG = AppConfig()
