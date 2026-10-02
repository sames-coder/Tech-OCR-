from pathlib import Path

from bankxat.discovery import discover_files


def test_discovery_deduplicates_by_hash(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("bir xil", encoding="utf-8")
    (tmp_path / "b.txt").write_text("bir xil", encoding="utf-8")
    (tmp_path / ".DS_Store").write_text("ignore", encoding="utf-8")

    files, summary = discover_files(tmp_path)

    assert len(files) == 2
    assert summary.unique_files == 1
    assert summary.duplicate_files == 1
    assert summary.skipped_system_files == 1
