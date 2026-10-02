"""Natija va review JSON fayllarini atomik yozish."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bankxat.models import ProcessedDocument
from bankxat.security import redact_identity_numbers


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """JSON'ni shu papkada vaqtinchalik fayl orqali atomik almashtiradi."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_documents(path: Path) -> list[dict[str, Any]]:
    """Mavjud natijalarni schema buzilgan bo'lsa xavfsiz rad etib yuklaydi."""

    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = payload.get("files", [])
    return files if isinstance(files, list) else []


def merge_results(output_dir: Path, documents: list[ProcessedDocument]) -> None:
    """Yangi hujjatlarni hash bo'yicha almashtirib results va review JSON'ga yozadi."""

    results_path = output_dir / "results.json"
    review_path = output_dir / "review_queue.json"
    existing = {item["file_sha256"]: item for item in _load_documents(results_path)}
    review_payload = (
        json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    )
    previous_reviews = review_payload.get("items", [])
    replaced_hashes = {document.file_sha256 for document in documents}
    reviews: list[dict[str, Any]] = [
        item
        for item in previous_reviews
        if isinstance(item, dict) and item.get("file_sha256") not in replaced_hashes
    ]
    for document in documents:
        serialized = document.model_dump(mode="json")
        existing[document.file_sha256] = serialized
        for item in document.review_items:
            reviews.append(
                {
                    "file_sha256": document.file_sha256,
                    "relative_path": document.relative_path,
                    "finding": item.model_dump(mode="json"),
                }
            )
    now = datetime.now(UTC).isoformat()
    _atomic_json_write(
        results_path,
        {"schema_version": "1.0", "updated_at": now, "files": list(existing.values())},
    )
    _atomic_json_write(
        review_path,
        {"schema_version": "1.0", "updated_at": now, "items": reviews},
    )


def public_results(output_dir: Path) -> list[dict[str, Any]]:
    """Faqat localhost UI uchun to'liq karta va audit dalilini qaytaradi."""

    groups: list[dict[str, Any]] = []
    for document in _load_documents(output_dir / "results.json"):
        cards: list[dict[str, Any]] = []
        for finding in document.get("findings", []):
            evidence = finding.get("evidence", {})
            cards.append(
                {
                    "card": finding.get("value"),
                    "card_masked": finding.get("value_masked"),
                    "position": finding.get("position"),
                    "role": finding.get("role"),
                    "role_confidence": finding.get("role_confidence"),
                    "role_source": finding.get("role_source", "rules"),
                    "ai_assisted": finding.get("ai_assisted", False),
                    "ai_evidence": finding.get("ai_evidence"),
                    "ai_reason": finding.get("ai_reason"),
                    "confidence": finding.get("confidence"),
                    "page": evidence.get("page"),
                    "snippet": redact_identity_numbers(str(evidence.get("snippet", ""))),
                    "source": evidence.get("source"),
                    "ocr_engines": evidence.get("ocr_engines", []),
                    "consensus_count": evidence.get("consensus_count", 0),
                    "validation": finding.get("validation", {}),
                    "warnings": finding.get("warnings", []),
                    "needs_review": bool(finding.get("needs_review", False))
                    or (
                        str(evidence.get("source", "")).startswith("ocr")
                        and finding.get("validation", {}).get("ocr_engines_agree") is not True
                    )
                    or float(finding.get("confidence", 0)) < 0.90
                    or finding.get("role") == "UNKNOWN"
                    or float(finding.get("role_confidence", 0)) < 0.80
                    or finding.get("role_source") in {"pair_order_fallback", "semantic_conflict"},
                }
            )
        if cards:
            groups.append(
                {
                    "relative_path": document.get("relative_path"),
                    "file_type": document.get("file_type"),
                    "status": document.get("status"),
                    "cards": cards,
                }
            )
    return groups


def public_review_items(output_dir: Path) -> list[dict[str, Any]]:
    """UI uchun tekshiruv navbatini maxfiy identifikatorlar yashirilgan holda qaytaradi."""

    path = output_dir / "review_queue.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: list[dict[str, Any]] = []
    for item in payload.get("items", []):
        finding = item.get("finding", {})
        evidence = finding.get("evidence", {})
        result.append(
            {
                "relative_path": item.get("relative_path"),
                "card": finding.get("value"),
                "role": finding.get("role"),
                "confidence": finding.get("confidence"),
                "page": evidence.get("page"),
                "source": evidence.get("source"),
                "snippet": redact_identity_numbers(str(evidence.get("snippet", ""))),
                "warnings": finding.get("warnings", []),
            }
        )
    return result


def review_count(output_dir: Path) -> int:
    """Web statistikasi uchun joriy review elementlari sonini qaytaradi."""

    path = output_dir / "review_queue.json"
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    return len(items) if isinstance(items, list) else 0


def clear_generated_files(output_dir: Path, uploads_directory: Path) -> None:
    """Faqat BankXat yaratgan natijalar va yuklangan nusxalarni o'chiradi."""

    for filename in ("results.json", "review_queue.json", "run_log.jsonl"):
        target = output_dir / filename
        if target.is_file():
            target.unlink()

    if uploads_directory.exists():
        for child in uploads_directory.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            elif child.is_file() or child.is_symlink():
                child.unlink()
    uploads_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
