"""Mahalliy tashqi dasturlar mavjudligini tekshirish."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import asdict, dataclass

from bankxat.config import Settings


@dataclass(frozen=True)
class ToolCheck:
    """Bitta tashqi vosita tekshiruvi."""

    name: str
    available: bool
    path: str | None
    required_now: bool
    install_hint: str


def check_tools(settings: Settings) -> list[ToolCheck]:
    """OCR va arxiv vositalarini PATH yoki konfiguratsiyadan qidiradi."""

    specs = [
        ("7-Zip", settings.archives.seven_zip_path, True, "macOS: brew install sevenzip"),
        ("Tesseract", settings.ocr.tesseract_path, False, "macOS: brew install tesseract"),
        (
            "LibreOffice",
            settings.ocr.libreoffice_path,
            False,
            "macOS: brew install --cask libreoffice",
        ),
    ]
    checks = [
        ToolCheck(
            name=name,
            available=(resolved := shutil.which(command)) is not None,
            path=resolved,
            required_now=required_now,
            install_hint=hint,
        )
        for name, command, required_now, hint in specs
    ]
    paddle_available = (
        importlib.util.find_spec("paddleocr") is not None
        and importlib.util.find_spec("paddle") is not None
    )
    checks.append(
        ToolCheck(
            name="PaddleOCR 3.x",
            available=paddle_available,
            path="Python package" if paddle_available else None,
            required_now=False,
            install_hint="python -m pip install -e '.[ocr]' (ixtiyoriy ikkinchi OCR)",
        )
    )
    ollama_path = shutil.which("ollama")
    checks.append(
        ToolCheck(
            name="AI yordamchi (Ollama)",
            available=ollama_path is not None,
            path=ollama_path,
            required_now=False,
            install_hint=(
                f"Ixtiyoriy: ollama.com dan o'rnating va {settings.ai.model} modelini yuklang"
            ),
        )
    )
    return checks


def checks_as_dicts(settings: Settings) -> list[dict[str, object]]:
    """Web API uchun tekshiruv natijalarini lug'atga aylantiradi."""

    return [asdict(item) for item in check_tools(settings)]
