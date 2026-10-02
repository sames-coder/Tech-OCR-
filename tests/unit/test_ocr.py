import pytest
from PIL import Image

from bankxat.config import Settings
from bankxat.textsource.ocr import preprocessing_variants, run_tesseract_variants


def test_preprocessing_builds_multiple_document_variants() -> None:
    image = Image.new("RGB", (40, 20), "white")

    variants = preprocessing_variants(image)

    assert set(variants) == {"original", "contrast", "binary", "upscale"}
    assert variants["upscale"].size == (80, 40)


def test_preprocessing_can_be_disabled() -> None:
    image = Image.new("RGB", (40, 20), "white")

    variants = preprocessing_variants(image, enabled=False)

    assert set(variants) == {"original"}


def test_tesseract_variants_keep_independent_consensus_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = Image.new("RGB", (40, 20), "white")
    monkeypatch.setattr(
        "bankxat.textsource.ocr._run_tesseract_variant",
        lambda _image, _settings, page_mode: (
            "Qabul qiluvchi 4111 1111 1111 1111" if page_mode == 6 else "matn"
        ),
    )

    results = run_tesseract_variants(image, Settings())

    assert "tesseract-original-psm6" in results
    assert "tesseract-contrast-psm6" in results
    assert len(results) > 2
