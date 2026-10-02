"""Rasmni tayyorlash va bir nechta lokal OCR natijasini yig'ish."""

from __future__ import annotations

import importlib
import importlib.util
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps

from bankxat.config import Settings

CARD_LIKE_PATTERN = re.compile(r"(?<![0-9])(?:[0-9][\s.\-]*){15}[0-9](?![0-9])")


def _card_values(text: str) -> set[str]:
    return {re.sub(r"[\s.\-]", "", match) for match in CARD_LIKE_PATTERN.findall(text)}


def _otsu_threshold(image: Image.Image) -> int:
    """Kulrang rasm uchun Otsu chegarasini tashqi kutubxonasiz hisoblaydi."""

    histogram = image.histogram()[:256]
    total = sum(histogram)
    weighted_sum = sum(index * count for index, count in enumerate(histogram))
    background_weight = 0
    background_sum = 0
    best_variance = -1.0
    best_threshold = 127
    for threshold, count in enumerate(histogram):
        background_weight += count
        if background_weight == 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight == 0:
            break
        background_sum += threshold * count
        background_mean = background_sum / background_weight
        foreground_mean = (weighted_sum - background_sum) / foreground_weight
        variance = background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = threshold
    return best_threshold


def preprocessing_variants(image: Image.Image, enabled: bool = True) -> dict[str, Image.Image]:
    """OCR uchun original, kontrastli va binarizatsiyalangan variantlarni yaratadi."""

    rgb = ImageOps.exif_transpose(image).convert("RGB")
    if not enabled:
        return {"original": rgb}
    grayscale = ImageOps.grayscale(rgb)
    contrast = ImageOps.autocontrast(grayscale, cutoff=1).filter(ImageFilter.MedianFilter(3))
    threshold = _otsu_threshold(contrast)
    binary = contrast.point(lambda pixel: 255 if pixel > threshold else 0, mode="1").convert("L")
    upscale = contrast.resize(
        (contrast.width * 2, contrast.height * 2),
        Image.Resampling.LANCZOS,
    ).filter(ImageFilter.SHARPEN)
    return {
        "original": rgb,
        "contrast": contrast,
        "binary": binary,
        "upscale": upscale,
    }


def _text_quality(text: str) -> tuple[int, int, int]:
    """Karta nomzodi, raqamlar va foydali belgilar bo'yicha OCR matnini baholaydi."""

    cards = len(CARD_LIKE_PATTERN.findall(text))
    digits = sum(character.isdigit() for character in text)
    useful = sum(character.isalnum() for character in text)
    return cards, digits, useful


def _run_tesseract_variant(
    image: Image.Image,
    settings: Settings,
    page_mode: int,
) -> str:
    """Bitta tayyorlangan rasmni belgilangan Tesseract rejimida o'qiydi."""

    languages = "+".join(settings.ocr.languages)
    with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
        image.save(temporary.name)
        command = [
            settings.ocr.tesseract_path,
            temporary.name,
            "stdout",
            "-l",
            languages,
            "--psm",
            str(page_mode),
            "-c",
            "preserve_interword_spaces=1",
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.pipeline.file_timeout_seconds,
        )
        if result.returncode == 0:
            return result.stdout
        fallback = subprocess.run(
            [
                settings.ocr.tesseract_path,
                temporary.name,
                "stdout",
                "-l",
                "eng",
                "--psm",
                str(page_mode),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.pipeline.file_timeout_seconds,
        )
        if fallback.returncode != 0:
            raise RuntimeError("Tesseract hujjatni o'qiy olmadi")
        return fallback.stdout


def run_tesseract_variants(image: Image.Image, settings: Settings) -> dict[str, str]:
    """Har bir Tesseract preprocessing/PSM natijasini audit va konsensus uchun saqlaydi."""

    results: dict[str, str] = {}
    variants = preprocessing_variants(image, settings.ocr.preprocess)
    initial_names = [name for name in ("original", "contrast") if name in variants]
    for name in initial_names:
        for page_mode in settings.ocr.tesseract_page_modes:
            text = _run_tesseract_variant(variants[name], settings, page_mode)
            if text.strip():
                results[f"tesseract-{name}-psm{page_mode}"] = text

    card_sets = [_card_values(text) for text in results.values()]
    nonempty_sets = [frozenset(cards) for cards in card_sets if cards]
    set_counts = Counter(nonempty_sets)
    union = set().union(*card_sets) if card_sets else set()
    stable = any(count >= 2 and set(card_set) == union for card_set, count in set_counts.items())
    if not stable:
        for name in ("binary", "upscale"):
            if name not in variants:
                continue
            for page_mode in settings.ocr.tesseract_page_modes:
                text = _run_tesseract_variant(variants[name], settings, page_mode)
                if text.strip():
                    results[f"tesseract-{name}-psm{page_mode}"] = text
    return results


def run_tesseract_ensemble(image: Image.Image, settings: Settings) -> str:
    """Tesseract variantlaridan karta va matn sifati eng yuqori bo'lganini qaytaradi."""

    results = run_tesseract_variants(image, settings)
    return max(results.values(), key=_text_quality, default="")


def _paddle_text(result: Any) -> str:
    """PaddleOCR 3.x natijasidan matnlarni versiyaga bardoshli tarzda oladi."""

    payload = getattr(result, "json", None)
    if callable(payload):
        payload = payload()
    if not isinstance(payload, dict):
        return ""
    body = payload.get("res", payload)
    if not isinstance(body, dict):
        return ""
    texts = body.get("rec_texts", [])
    if isinstance(texts, list):
        return "\n".join(str(text) for text in texts if str(text).strip())
    return ""


def run_paddle(image: Image.Image, settings: Settings) -> str | None:
    """Sozlangan va o'rnatilgan bo'lsa lokal PaddleOCR natijasini qaytaradi."""

    if (
        not settings.ocr.paddle_enabled
        or importlib.util.find_spec("paddleocr") is None
        or importlib.util.find_spec("paddle") is None
    ):
        return None
    module = importlib.import_module("paddleocr")
    paddle_class = module.PaddleOCR
    engine = paddle_class(
        lang=settings.ocr.paddle_language,
        ocr_version="PP-OCRv5",
        use_doc_orientation_classify=True,
        use_doc_unwarping=True,
        use_textline_orientation=True,
    )
    with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
        ImageOps.exif_transpose(image).convert("RGB").save(temporary.name)
        results = engine.predict(temporary.name)
    texts = [_paddle_text(result) for result in results]
    combined = "\n".join(text for text in texts if text)
    return combined or None


def run_ocr_ensemble(image: Image.Image, settings: Settings) -> dict[str, str]:
    """Mavjud lokal OCR engine'larini ishga tushirib engine bo'yicha matn qaytaradi."""

    outputs = run_tesseract_variants(image, settings)
    paddle_text = run_paddle(image, settings)
    if paddle_text:
        outputs["paddleocr"] = paddle_text
    return outputs


def open_image(path: Path) -> Image.Image:
    """Rasmni fayl deskriptoridan uzilgan nusxa sifatida ochadi."""

    with Image.open(path) as image:
        return image.copy()
