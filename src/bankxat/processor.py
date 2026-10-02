"""Matn olishdan JSON natijagacha bo'lgan boshlang'ich processing pipeline."""

from __future__ import annotations

import tempfile
from pathlib import Path

from bankxat.archives import extract_archive
from bankxat.config import Settings
from bankxat.discovery import sha256_file
from bankxat.extract.candidates import apply_pair_order_roles, find_card_candidates
from bankxat.models import FileStatus, ProcessedDocument, Role
from bankxat.output import merge_results
from bankxat.semantic import SemanticAssistant, apply_semantic_roles
from bankxat.textsource.extract import extract_pages


def _process_file(
    path: Path,
    relative_path: str,
    settings: Settings,
    depth: int,
    assistant: SemanticAssistant,
) -> list[ProcessedDocument]:
    """Bitta faylni yoki arxiv ichidagi fayllarni rekursiv qayta ishlaydi."""

    digest = sha256_file(path)
    try:
        document_type, pages = extract_pages(path, settings)
        if document_type == "archive":
            if depth >= settings.archives.max_depth:
                raise RuntimeError("Arxiv chuqurligi limitdan oshdi")
            with tempfile.TemporaryDirectory(prefix="bankxat-archive-") as directory:
                extracted_root = Path(directory)
                extract_archive(path, extracted_root, settings)
                nested: list[ProcessedDocument] = []
                for child in sorted(item for item in extracted_root.rglob("*") if item.is_file()):
                    nested_path = child.relative_to(extracted_root).as_posix()
                    child_relative = f"{relative_path} > {nested_path}"
                    nested.extend(
                        _process_file(child, child_relative, settings, depth + 1, assistant)
                    )
                return nested

        candidates = [candidate for page in pages for candidate in find_card_candidates(page)]
        if settings.pipeline.card_role_strategy == "pair_order":
            candidates = apply_pair_order_roles(candidates)
        candidates = apply_semantic_roles(candidates, assistant.analyze(pages, candidates))
        valid_cards = [
            item
            for item in candidates
            if item.validation.luhn is True
            and item.validation.format_valid
            and item.validation.verified_in_source
        ]
        review = [
            item
            for item in candidates
            if item not in valid_cards
            or item.confidence < settings.pipeline.auto_accept_threshold
            or item.role is Role.UNKNOWN
            or item.role_confidence < 0.80
            or item.role_source in {"pair_order_fallback", "semantic_conflict"}
            or (
                item.evidence.source.startswith("ocr")
                and item.validation.ocr_engines_agree is not True
            )
        ]
        review_ids = {id(item) for item in review}
        for item in candidates:
            item.needs_review = id(item) in review_ids
        if review:
            status = FileStatus.NEEDS_REVIEW
        elif valid_cards:
            status = FileStatus.FOUND_CARD
        elif document_type == "unsupported" or not pages:
            status = FileStatus.SKIPPED_UNSUPPORTED
        else:
            status = FileStatus.SKIPPED_NO_DATA
        return [
            ProcessedDocument(
                source_path=str(path),
                relative_path=relative_path,
                file_sha256=digest,
                file_type=document_type,
                status=status,
                findings=valid_cards,
                review_items=review,
            )
        ]
    except Exception as exc:
        return [
            ProcessedDocument(
                source_path=str(path),
                relative_path=relative_path,
                file_sha256=digest,
                file_type="error",
                status=FileStatus.ERROR,
                warnings=[type(exc).__name__],
            )
        ]


def process_directory(
    root: Path, settings: Settings
) -> tuple[list[ProcessedDocument], dict[str, int]]:
    """Papka hujjatlarini o'qib, ishonchli karta va review holatlarini saqlaydi."""

    documents: list[ProcessedDocument] = []
    assistant = SemanticAssistant(settings.ai)
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative_path = path.relative_to(root).as_posix()
        documents.extend(_process_file(path, relative_path, settings, depth=0, assistant=assistant))
    merge_results(settings.app.output_dir, documents)
    stats = {
        "processed": len(documents),
        "found_cards": sum(len(item.findings) for item in documents),
        "ai_assisted": sum(
            finding.ai_assisted for document in documents for finding in document.findings
        ),
        "needs_review": sum(len(item.review_items) for item in documents),
        "errors": sum(item.status is FileStatus.ERROR for item in documents),
    }
    return documents, stats
