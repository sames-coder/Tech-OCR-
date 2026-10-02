"""Resume va web hisobotlari uchun SQLite holat ombori."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from bankxat.models import DiscoveredFile, ScanSummary

SCHEMA_VERSION = 1


class StateStore:
    """SQLite ulanishlarini qisqa tranzaksiyalarda boshqaradi."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Foreign key va WAL yoqilgan ulanishni qaytaradi."""

        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Idempotent holat sxemasini yaratadi."""

        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    input_root TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    files_seen INTEGER NOT NULL,
                    unique_files INTEGER NOT NULL,
                    duplicate_files INTEGER NOT NULL,
                    skipped_system_files INTEGER NOT NULL,
                    total_bytes INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    source_path TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    modified_at TEXT NOT NULL,
                    duplicate_of TEXT,
                    processing_status TEXT NOT NULL DEFAULT 'DISCOVERED',
                    UNIQUE(run_id, source_path)
                );
                CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);
                CREATE INDEX IF NOT EXISTS idx_files_run_id ON files(run_id);
                CREATE TABLE IF NOT EXISTS review_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                    item_type TEXT NOT NULL,
                    masked_value TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def save_scan(self, files: list[DiscoveredFile], summary: ScanSummary) -> None:
        """Bitta inventarizatsiya natijasini atomik tranzaksiyada saqlaydi."""

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.run_id,
                    str(summary.input_root),
                    summary.started_at.isoformat(),
                    summary.finished_at.isoformat(),
                    summary.files_seen,
                    summary.unique_files,
                    summary.duplicate_files,
                    summary.skipped_system_files,
                    summary.total_bytes,
                ),
            )
            connection.executemany(
                """
                INSERT INTO files(
                    run_id, source_path, relative_path, sha256, size_bytes,
                    modified_at, duplicate_of
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        summary.run_id,
                        str(item.source_path),
                        str(item.relative_path),
                        item.sha256,
                        item.size_bytes,
                        item.modified_at.isoformat(),
                        str(item.duplicate_of) if item.duplicate_of else None,
                    )
                    for item in files
                ],
            )

    def dashboard(self) -> dict[str, Any]:
        """Boshqaruv paneli uchun agregatlarni qaytaradi."""

        with self.connect() as connection:
            latest = connection.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            totals = connection.execute(
                """
                SELECT COUNT(*) AS runs,
                       COALESCE(SUM(unique_files), 0) AS files,
                       COALESCE(SUM(duplicate_files), 0) AS duplicates
                FROM runs
                """
            ).fetchone()
            pending = connection.execute(
                "SELECT COUNT(*) AS count FROM review_items WHERE resolved_at IS NULL"
            ).fetchone()
        return {
            "runs": totals["runs"],
            "files": totals["files"],
            "duplicates": totals["duplicates"],
            "pending_review": pending["count"],
            "latest_run": dict(latest) if latest else None,
        }

    def recent_files(self, limit: int = 20) -> list[dict[str, Any]]:
        """So'nggi inventarizatsiyadagi fayllarni qaytaradi."""

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT relative_path, size_bytes, processing_status, duplicate_of, sha256
                FROM files
                WHERE run_id = (SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1)
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_processing_data(self) -> None:
        """Sxemani saqlagan holda barcha run, fayl va review yozuvlarini o'chiradi."""

        with self.connect() as connection:
            connection.execute("DELETE FROM review_items")
            connection.execute("DELETE FROM files")
            connection.execute("DELETE FROM runs")
            connection.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('files', 'review_items')"
            )
