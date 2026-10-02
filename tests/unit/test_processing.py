import json
import zipfile
from pathlib import Path

import pytest

from bankxat.archives import ArchiveError, extract_archive
from bankxat.config import AppConfig, Settings, UploadConfig
from bankxat.extract.candidates import find_card_candidates
from bankxat.models import ExtractedPage, Role
from bankxat.output import public_results
from bankxat.processor import process_directory


def test_role_classifier_distinguishes_sender_and_recipient() -> None:
    page = ExtractedPage(
        page=1,
        source="text_layer",
        text=(
            "4111 1111 1111 1111 kartasidan 4012 8888 8888 1881 kartasiga 250 000 so'm o'tkazilgan."
        ),
    )

    candidates = find_card_candidates(page)

    assert [item.role for item in candidates] == [Role.SENDER, Role.RECIPIENT]


@pytest.mark.parametrize(
    ("text", "roles"),
    [
        (
            "Pul 4111 1111 1111 1111 hisobidan chiqarilib, "
            "4012 8888 8888 1881 hisobiga yo'naltirildi.",
            [Role.SENDER, Role.RECIPIENT],
        ),
        (
            "Карта отправителя: 4111 1111 1111 1111. Карта получателя: 4012 8888 8888 1881.",
            [Role.SENDER, Role.RECIPIENT],
        ),
        (
            "Beneficiary 4012 8888 8888 1881; payer 4111 1111 1111 1111.",
            [Role.RECIPIENT, Role.SENDER],
        ),
    ],
)
def test_role_classifier_handles_different_letter_wording(text: str, roles: list[Role]) -> None:
    candidates = find_card_candidates(ExtractedPage(page=1, source="text_layer", text=text))

    assert [item.role for item in candidates] == roles


def test_two_ocr_engines_create_consensus() -> None:
    text = "4111111111111111 dan 4012888888881881 ga"
    page = ExtractedPage(
        page=1,
        source="ocr_ensemble",
        text=text,
        ocr_variants={"tesseract": text, "paddleocr": text},
        ocr_verified=True,
    )

    candidates = find_card_candidates(page)

    assert all(item.validation.ocr_engines_agree is True for item in candidates)
    assert all(item.evidence.consensus_count == 2 for item in candidates)


def test_processor_writes_full_json_and_returns_local_full_web_result(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "xat.txt").write_text(
        "4111 1111 1111 1111 kartasidan 4012 8888 8888 1881 kartasiga o'tkazildi",
        encoding="utf-8",
    )
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data/state.sqlite",
        ),
        uploads=UploadConfig(directory=tmp_path / "uploads"),
    )

    _, stats = process_directory(input_dir, settings)

    assert stats["found_cards"] == 2
    payload = json.loads((tmp_path / "output/results.json").read_text(encoding="utf-8"))
    findings = payload["files"][0]["findings"]
    assert [item["value"] for item in findings] == [
        "4111111111111111",
        "4012888888881881",
    ]
    assert [item["role"] for item in findings] == ["SENDER", "RECIPIENT"]
    assert [item["position"] for item in findings] == [1, 2]
    web_results = public_results(tmp_path / "output")
    assert web_results[0]["relative_path"] == "xat.txt"
    assert [item["card"] for item in web_results[0]["cards"]] == [
        "4111111111111111",
        "4012888888881881",
    ]
    assert "4012888888881881" in json.dumps(web_results)
    assert web_results[0]["cards"][0]["card_masked"] == "4111 **** **** 1111"


def test_pair_order_strategy_stores_every_card_and_assigns_roles(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "tort_karta.txt").write_text(
        "4111111111111111 birinchi 4012888888881881 ikkinchi "
        "5555555555554444 uchinchi 4000000000000002 to'rtinchi",
        encoding="utf-8",
    )
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data/state.sqlite",
        ),
        uploads=UploadConfig(directory=tmp_path / "uploads"),
    )

    documents, stats = process_directory(input_dir, settings)

    assert stats["found_cards"] == 4
    assert [item.value for item in documents[0].findings] == [
        "4111111111111111",
        "4012888888881881",
        "5555555555554444",
        "4000000000000002",
    ]
    assert [item.position for item in documents[0].findings] == [1, 2, 3, 4]
    assert [item.role for item in documents[0].findings] == [
        Role.SENDER,
        Role.RECIPIENT,
        Role.SENDER,
        Role.RECIPIENT,
    ]
    assert all(item.role_source == "pair_order_fallback" for item in documents[0].findings)
    assert all(item.needs_review for item in documents[0].findings)
    assert stats["needs_review"] == 4


def test_invalid_card_keeps_document_in_review_status(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "aralash.txt").write_text(
        "4111111111111111 kartadan 4111111111111112 kartaga",
        encoding="utf-8",
    )
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data/state.sqlite",
        ),
        uploads=UploadConfig(directory=tmp_path / "uploads"),
        ai={"enabled": False},
    )

    documents, stats = process_directory(input_dir, settings)

    assert documents[0].status.value == "NEEDS_REVIEW"
    assert stats["found_cards"] == 1
    assert stats["needs_review"] == 1


def test_ocr_card_is_stored_but_flagged_for_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "skaner.png").write_bytes(b"fake-image")
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data/state.sqlite",
        ),
        uploads=UploadConfig(directory=tmp_path / "uploads"),
    )

    monkeypatch.setattr(
        "bankxat.processor.extract_pages",
        lambda _path, _settings: (
            "image",
            [
                ExtractedPage(
                    page=1,
                    source="ocr_tesseract",
                    text="4111111111111111 dan 4012888888881881 ga",
                )
            ],
        ),
    )

    documents, stats = process_directory(input_dir, settings)

    assert stats["found_cards"] == 2
    assert stats["needs_review"] == 2
    assert len(documents[0].findings) == 2
    assert len(documents[0].review_items) == 2
    assert all(item["needs_review"] for item in public_results(tmp_path / "output")[0]["cards"])


def test_zip_archive_is_processed_recursively(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    archive = input_dir / "xatlar.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(
            "ichki/xat.txt",
            "4111111111111111 kartasidan 4012888888881881 kartasiga o'tkazildi",
        )
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data/state.sqlite",
        ),
        uploads=UploadConfig(directory=tmp_path / "uploads"),
    )

    documents, stats = process_directory(input_dir, settings)

    assert stats["found_cards"] == 2
    assert documents[0].relative_path == "xatlar.zip > ichki/xat.txt"


def test_archive_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "xavfli.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../tashqarida.txt", "x")
    settings = Settings(uploads=UploadConfig(directory=tmp_path / "uploads"))

    with pytest.raises(ArchiveError, match="xavfli yo'l"):
        extract_archive(archive, tmp_path / "extracted", settings)
