"""Kirish papkasini xavfsiz inventarizatsiya qilish."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bankxat.models import DiscoveredFile, ScanSummary

SYSTEM_PARTS = frozenset({"__MACOSX"})
SYSTEM_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
HASH_CHUNK_SIZE = 1024 * 1024


def is_system_path(path: Path) -> bool:
    """Operatsion tizim yaratgan xizmat faylini aniqlaydi."""

    return path.name in SYSTEM_FILES or any(part in SYSTEM_PARTS for part in path.parts)


def sha256_file(path: Path) -> str:
    """Faylni xotiraga to'liq yuklamasdan SHA-256 hisoblaydi."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def iter_regular_files(root: Path) -> Iterator[Path]:
    """Symlinklarni kuzatmasdan oddiy fayllarni tartibli qaytaradi."""

    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        yield path


def discover_files(root: Path) -> tuple[list[DiscoveredFile], ScanSummary]:
    """Papka fayllarini hash bilan topadi va nusxalarni belgilaydi."""

    resolved_root = root.expanduser().resolve()
    if not resolved_root.exists():
        raise FileNotFoundError(f"Kirish papkasi topilmadi: {resolved_root}")
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"Kirish yo'li papka emas: {resolved_root}")

    started_at = datetime.now(UTC)
    run_id = f"scan-{started_at.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
    seen_hashes: dict[str, Path] = {}
    discovered: list[DiscoveredFile] = []
    skipped_system_files = 0
    total_bytes = 0

    for path in iter_regular_files(resolved_root):
        relative_path = path.relative_to(resolved_root)
        if is_system_path(relative_path):
            skipped_system_files += 1
            continue
        stat = path.stat()
        digest = sha256_file(path)
        duplicate_of = seen_hashes.get(digest)
        if duplicate_of is None:
            seen_hashes[digest] = relative_path
        total_bytes += stat.st_size
        discovered.append(
            DiscoveredFile(
                source_path=path,
                relative_path=relative_path,
                sha256=digest,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                duplicate_of=duplicate_of,
            )
        )

    duplicate_count = sum(item.duplicate_of is not None for item in discovered)
    summary = ScanSummary(
        run_id=run_id,
        input_root=resolved_root,
        files_seen=len(discovered),
        unique_files=len(discovered) - duplicate_count,
        duplicate_files=duplicate_count,
        skipped_system_files=skipped_system_files,
        total_bytes=total_bytes,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    return discovered, summary
