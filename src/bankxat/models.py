"""Pipeline bo'ylab ishlatiladigan qat'iy ma'lumot modellari."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class FileStatus(StrEnum):
    """Fayl qayta ishlashining yakuniy holati."""

    FOUND_CARD = "FOUND_CARD"
    FOUND_PINFL = "FOUND_PINFL"
    FOUND_OTHER = "FOUND_OTHER"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SKIPPED_NO_DATA = "SKIPPED_NO_DATA"
    SKIPPED_UNSUPPORTED = "SKIPPED_UNSUPPORTED"
    ERROR = "ERROR"


class Role(StrEnum):
    """Karta yoki shaxsning o'tkazmadagi roli."""

    SENDER = "SENDER"
    RECIPIENT = "RECIPIENT"
    UNKNOWN = "UNKNOWN"


class FindingType(StrEnum):
    """Topilgan ma'lumot turi."""

    CARD = "card"
    RECIPIENT_CARD = "recipient_card"
    PINFL = "pinfl"
    PHONE = "phone"
    PERSON_NAME = "person_name"
    PASSPORT = "passport"


class BoundingBox(BaseModel):
    """Hujjat sahifasidagi to'rtburchak koordinata."""

    x0: float
    y0: float
    x1: float
    y1: float


class Evidence(BaseModel):
    """Topilmani manba bilan bog'lovchi audit dalili."""

    page: int = Field(ge=1)
    snippet: str
    bbox: BoundingBox | None = None
    source: str = "text_layer"
    ocr_engines: list[str] = Field(default_factory=list)
    consensus_count: int = Field(default=0, ge=0)


class ValidationResult(BaseModel):
    """Nomzod ustida bajarilgan tekshiruvlar."""

    luhn: bool | None = None
    verified_in_source: bool
    ocr_engines_agree: bool | None = None
    format_valid: bool = True


class Finding(BaseModel):
    """Bitta tasdiqlangan yoki ko'rib chiqiladigan topilma."""

    type: FindingType
    value: str
    value_masked: str
    position: int | None = Field(default=None, ge=1)
    role: Role = Role.UNKNOWN
    role_confidence: float = Field(default=0, ge=0, le=1)
    role_source: str = "rules"
    ai_assisted: bool = False
    ai_evidence: str | None = None
    ai_reason: str | None = None
    needs_review: bool = False
    confidence: float = Field(ge=0, le=1)
    validation: ValidationResult
    evidence: Evidence
    warnings: list[str] = Field(default_factory=list)


class DiscoveredFile(BaseModel):
    """Inventarizatsiyada topilgan fayl metama'lumotlari."""

    source_path: Path
    relative_path: Path
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    modified_at: datetime
    duplicate_of: Path | None = None


class ScanSummary(BaseModel):
    """Inventarizatsiya natijasining qisqa hisoboti."""

    run_id: str
    input_root: Path
    files_seen: int
    unique_files: int
    duplicate_files: int
    skipped_system_files: int
    total_bytes: int
    started_at: datetime
    finished_at: datetime

    @classmethod
    def empty(cls, run_id: str, input_root: Path) -> ScanSummary:
        """Bo'sh, ammo vaqt jihatdan to'g'ri hisobot yaratadi."""

        now = datetime.now(UTC)
        return cls(
            run_id=run_id,
            input_root=input_root,
            files_seen=0,
            unique_files=0,
            duplicate_files=0,
            skipped_system_files=0,
            total_bytes=0,
            started_at=now,
            finished_at=now,
        )


class ExtractedPage(BaseModel):
    """Bitta sahifadan olingan matn va uning kelib chiqishi."""

    page: int = Field(ge=1)
    text: str
    source: str
    ocr_verified: bool = False
    ocr_variants: dict[str, str] = Field(default_factory=dict)


class ProcessedDocument(BaseModel):
    """Bitta hujjat bo'yicha ajratish yakuni."""

    source_path: str
    relative_path: str
    file_sha256: str
    file_type: str
    status: FileStatus
    findings: list[Finding] = Field(default_factory=list)
    review_items: list[Finding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
