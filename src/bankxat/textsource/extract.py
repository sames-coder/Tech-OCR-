"""Hujjat turini aniqlash va lokal matn olish."""

from __future__ import annotations

import subprocess
import tempfile
import zipfile
from pathlib import Path

import filetype  # type: ignore[import-untyped]
import pdfplumber
import pypdfium2 as pdfium  # type: ignore[import-untyped]
from docx import Document

from bankxat.config import Settings
from bankxat.models import ExtractedPage
from bankxat.textsource.ocr import CARD_LIKE_PATTERN, open_image, run_ocr_ensemble


def detect_document_type(path: Path) -> str:
    """Kengaytma va ichki imzo yordamida qo'llab-quvvatlanadigan turni aniqlaydi."""

    kind = filetype.guess(path)
    mime = kind.mime if kind else ""
    suffix = path.suffix.lower()
    with path.open("rb") as stream:
        signature = stream.read(16)
    if mime == "application/pdf" or signature.startswith(b"%PDF-"):
        return "pdf"
    if suffix == ".docx" and zipfile.is_zipfile(path):
        return "docx"
    if mime.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return "image"
    if suffix in {".txt", ".md", ".csv"}:
        return "text"
    if suffix == ".doc":
        return "doc"
    if suffix in {".zip", ".rar", ".7z"} or mime in {
        "application/zip",
        "application/x-rar-compressed",
        "application/x-7z-compressed",
    }:
        return "archive"
    return "unsupported"


def _primary_ocr_text(outputs: dict[str, str]) -> str:
    """Karta va foydali belgilar soni bo'yicha asosiy OCR matnini tanlaydi."""

    def score(text: str) -> tuple[int, int, int]:
        return (
            len(CARD_LIKE_PATTERN.findall(text)),
            sum(character.isdigit() for character in text),
            len(text.strip()),
        )

    return max(outputs.values(), key=score, default="")


def _extract_pdf(path: Path, settings: Settings) -> list[ExtractedPage]:
    """PDF matn qatlamini oladi, bo'sh sahifani Tesseract bilan o'qiydi."""

    extracted: list[ExtractedPage] = []
    render_document = pdfium.PdfDocument(path)
    try:
        with pdfplumber.open(path) as pdf:
            for index, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                source = "text_layer"
                compact_length = len("".join(text.split()))
                image_only_cards_possible = bool(page.images) and not CARD_LIKE_PATTERN.search(text)
                if compact_length < 30 or image_only_cards_possible:
                    bitmap = render_document[index].render(scale=settings.ocr.dpi / 72)
                    image = bitmap.to_pil()
                    outputs = run_ocr_ensemble(image, settings)
                    text = _primary_ocr_text(outputs)
                    source = "ocr_ensemble"
                else:
                    outputs = {}
                extracted.append(
                    ExtractedPage(
                        page=index + 1,
                        text=text,
                        source=source,
                        ocr_verified=len(outputs) >= settings.ocr.minimum_consensus_engines,
                        ocr_variants=outputs,
                    )
                )
    finally:
        render_document.close()
    return extracted


def _extract_docx(path: Path, settings: Settings) -> list[ExtractedPage]:
    """DOCX matni, jadvali, header/footer va ichki rasmlarini o'qiydi."""

    document = Document(str(path))
    chunks = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            chunks.append(" | ".join(cell.text for cell in row.cells))
    for section in document.sections:
        chunks.extend(
            paragraph.text for paragraph in section.header.paragraphs if paragraph.text.strip()
        )
        chunks.extend(
            paragraph.text for paragraph in section.footer.paragraphs if paragraph.text.strip()
        )
    ocr_outputs: dict[str, list[str]] = {}
    with zipfile.ZipFile(path) as archive:
        for member in sorted(name for name in archive.namelist() if name.startswith("word/media/")):
            with tempfile.NamedTemporaryFile(suffix=Path(member).suffix) as temporary:
                temporary.write(archive.read(member))
                temporary.flush()
                try:
                    outputs = run_ocr_ensemble(open_image(Path(temporary.name)), settings)
                except Exception:
                    continue
                for engine, text in outputs.items():
                    ocr_outputs.setdefault(engine, []).append(text)
                    chunks.append(text)
    variants = {engine: "\n".join(texts) for engine, texts in ocr_outputs.items()}
    return [
        ExtractedPage(
            page=1,
            text="\n".join(chunks),
            source="docx_with_ocr" if variants else "docx",
            ocr_verified=len(variants) >= settings.ocr.minimum_consensus_engines,
            ocr_variants=variants,
        )
    ]


def _extract_legacy_doc(path: Path, settings: Settings) -> list[ExtractedPage]:
    """Eski DOC faylini vaqtincha DOCX'ga aylantirib, umumiy pipeline'da o'qiydi."""

    with tempfile.TemporaryDirectory(prefix="bankxat-doc-") as directory:
        output_directory = Path(directory)
        result = subprocess.run(
            [
                settings.ocr.libreoffice_path,
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                str(output_directory),
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.pipeline.file_timeout_seconds,
        )
        converted = output_directory / f"{path.stem}.docx"
        if result.returncode != 0 or not converted.exists():
            raise RuntimeError("LibreOffice DOC faylini DOCX'ga aylantira olmadi")
        return _extract_docx(converted, settings)


def extract_pages(path: Path, settings: Settings) -> tuple[str, list[ExtractedPage]]:
    """Fayl turiga mos matn olish strategiyasini tanlaydi."""

    document_type = detect_document_type(path)
    if document_type == "pdf":
        return document_type, _extract_pdf(path, settings)
    if document_type == "docx":
        return document_type, _extract_docx(path, settings)
    if document_type == "doc":
        return document_type, _extract_legacy_doc(path, settings)
    if document_type == "image":
        outputs = run_ocr_ensemble(open_image(path), settings)
        return document_type, [
            ExtractedPage(
                page=1,
                text=_primary_ocr_text(outputs),
                source="ocr_ensemble",
                ocr_verified=len(outputs) >= settings.ocr.minimum_consensus_engines,
                ocr_variants=outputs,
            )
        ]
    if document_type == "text":
        return document_type, [
            ExtractedPage(
                page=1,
                text=path.read_text(encoding="utf-8", errors="replace"),
                source="text",
            )
        ]
    return document_type, []
