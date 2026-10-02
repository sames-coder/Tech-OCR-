"""7-Zip orqali arxivlarni oldindan tekshirib, xavfsiz ochish."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

from bankxat.config import Settings


class ArchiveError(RuntimeError):
    """Arxiv xavfsiz yoki to'liq ochilmaganda qaytariladigan xato."""


def _parse_listing(output: str) -> list[dict[str, str]]:
    """7-Zip `-slt` texnik ro'yxatini yozuvlarga ajratadi."""

    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        if " = " in line:
            key, value = line.split(" = ", maxsplit=1)
            current[key] = value
    if current:
        records.append(current)
    return records


def _safe_member_path(raw_path: str) -> PurePosixPath:
    """Arxiv ichidagi yo'lni absolyut va traversal qismlarga tekshiradi."""

    normalized = raw_path.replace("\\", "/")
    member = PurePosixPath(normalized)
    if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
        raise ArchiveError("Arxiv ichida xavfli yo'l topildi")
    return member


def extract_archive(path: Path, destination: Path, settings: Settings) -> None:
    """Arxivni hajm, son, shifrlash va yo'l tekshiruvidan keyin ochadi."""

    list_result = subprocess.run(
        [settings.archives.seven_zip_path, "l", "-slt", "-ba", str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=settings.pipeline.file_timeout_seconds,
    )
    if list_result.returncode != 0:
        raise ArchiveError("Arxiv tarkibini o'qib bo'lmadi")

    file_count = 0
    total_size = 0
    for record in _parse_listing(list_result.stdout):
        raw_member = record.get("Path")
        if not raw_member:
            continue
        _safe_member_path(raw_member)
        if record.get("Encrypted") == "+":
            raise ArchiveError("Parolli arxiv ochilmadi")
        if "Symbolic Link" in record:
            raise ArchiveError("Arxivdagi symlink qabul qilinmaydi")
        if record.get("Folder") != "+":
            file_count += 1
            try:
                total_size += int(record.get("Size", "0"))
            except ValueError as exc:
                raise ArchiveError("Arxiv hajmi noto'g'ri ko'rsatilgan") from exc

    if file_count > settings.archives.max_files:
        raise ArchiveError("Arxivdagi fayllar soni limitdan oshdi")
    if total_size > settings.archives.max_uncompressed_bytes:
        raise ArchiveError("Arxiv ochilgan hajmi limitdan oshdi")

    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    extract_result = subprocess.run(
        [
            settings.archives.seven_zip_path,
            "x",
            "-y",
            "-bd",
            "-bb0",
            f"-o{destination}",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=settings.pipeline.file_timeout_seconds,
    )
    if extract_result.returncode != 0:
        raise ArchiveError("Arxivni ochish yakunlanmadi")

    resolved_destination = destination.resolve()
    for extracted in destination.rglob("*"):
        if extracted.is_symlink():
            raise ArchiveError("Ochilgan arxivda symlink topildi")
        if not extracted.resolve().is_relative_to(resolved_destination):
            raise ArchiveError("Ochilgan fayl maqsad papkadan tashqariga chiqdi")
