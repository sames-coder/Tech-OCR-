"""Tizim sozlamalarini xavfsiz yuklash va tekshirish."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AppConfig(BaseModel):
    """Ilovaning asosiy yo'llari."""

    name: str = "Tech OCR"
    data_dir: Path = Path("data")
    output_dir: Path = Path("output")
    database_path: Path = Path("data/state.sqlite")


class WebConfig(BaseModel):
    """Lokal web server sozlamalari."""

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)


class UploadConfig(BaseModel):
    """Brauzerdan lokal yuklanadigan fayllar uchun xavfsizlik chegaralari."""

    directory: Path = Path("data/uploads")
    max_files_per_batch: int = Field(default=500, ge=1, le=5000)
    max_file_bytes: int = Field(default=52_428_800, ge=1)


class PipelineConfig(BaseModel):
    """Pipeline ishlash chegaralari."""

    workers: int = Field(default=2, ge=1, le=32)
    auto_accept_threshold: float = Field(default=0.90, ge=0, le=1)
    card_role_strategy: Literal["pair_order", "context"] = "pair_order"
    collect_auxiliary: bool = False
    file_timeout_seconds: int = Field(default=180, ge=10)


class ArchiveConfig(BaseModel):
    """Arxivlarni ochish xavfsizlik chegaralari."""

    max_depth: int = Field(default=10, ge=1, le=50)
    max_files: int = Field(default=10_000, ge=1)
    max_uncompressed_bytes: int = Field(default=2_147_483_648, ge=1)
    seven_zip_path: str = "7zz"


class OcrConfig(BaseModel):
    """OCR vositalari va render parametrlari."""

    dpi: int = Field(default=300, ge=150, le=600)
    languages: list[str] = Field(default_factory=lambda: ["uzb", "uzb_cyrl", "rus", "eng"])
    tesseract_path: str = "tesseract"
    libreoffice_path: str = "libreoffice"
    paddle_enabled: bool = False
    paddle_language: str = "uz"
    preprocess: bool = True
    tesseract_page_modes: list[int] = Field(default_factory=lambda: [6, 11])
    minimum_consensus_engines: int = Field(default=2, ge=1, le=3)


class AiConfig(BaseModel):
    """Asosiy pipeline'dan mustaqil ishlaydigan lokal AI yordamchi sozlamalari."""

    enabled: bool = False
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:1.7b"
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    minimum_confidence: float = Field(default=0.75, ge=0, le=1)
    max_text_characters: int = Field(default=12_000, ge=1_000, le=200_000)

    @field_validator("base_url")
    @classmethod
    def require_local_ollama(cls, value: str) -> str:
        """Maxfiy xatlar tasodifan masofaviy AI xizmatiga yuborilishini taqiqlaydi."""

        normalized = value.rstrip("/")
        allowed = ("http://127.0.0.1:", "http://localhost:", "http://[::1]:")
        if not normalized.startswith(allowed):
            raise ValueError("AI yordamchi faqat localhost manzilida ishlashi mumkin")
        return normalized


class Settings(BaseModel):
    """Barcha konfiguratsiya bo'limlarining yagona modeli."""

    app: AppConfig = Field(default_factory=AppConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    uploads: UploadConfig = Field(default_factory=UploadConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    archives: ArchiveConfig = Field(default_factory=ArchiveConfig)
    ocr: OcrConfig = Field(default_factory=OcrConfig)
    ai: AiConfig = Field(default_factory=AiConfig)

    @field_validator("app")
    @classmethod
    def normalize_paths(cls, value: AppConfig) -> AppConfig:
        """Yo'llarni foydalanuvchi uy papkasini hisobga olib normallashtiradi."""

        value.data_dir = value.data_dir.expanduser()
        value.output_dir = value.output_dir.expanduser()
        value.database_path = value.database_path.expanduser()
        return value

    @field_validator("uploads")
    @classmethod
    def normalize_upload_path(cls, value: UploadConfig) -> UploadConfig:
        """Yuklash papkasini foydalanuvchi uy papkasini hisobga olib normallashtiradi."""

        value.directory = value.directory.expanduser()
        return value

    def prepare_directories(self) -> None:
        """Faqat ish vaqtida kerak bo'lgan lokal papkalarni yaratadi."""

        self.app.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.app.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.app.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.uploads.directory.mkdir(parents=True, exist_ok=True, mode=0o700)


def load_settings(config_path: Path | None = None) -> Settings:
    """TOML fayldan sozlamalarni yuklaydi; fayl berilmasa standartlarni ishlatadi."""

    if config_path is None:
        default_path = Path("config/default.toml")
        if not default_path.exists():
            return Settings()
        config_path = default_path

    with config_path.open("rb") as stream:
        raw: dict[str, Any] = tomllib.load(stream)
    return Settings.model_validate(raw)
