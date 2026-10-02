"""BankXat buyruq qatori interfeysi."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from bankxat.config import load_settings
from bankxat.discovery import discover_files
from bankxat.logging_setup import configure_logging
from bankxat.selftest import check_tools
from bankxat.store import StateStore

app = typer.Typer(no_args_is_help=True, help="Tech OCR lokal bank xatlari protsessori")


@app.command()
def scan(
    input_path: Annotated[Path, typer.Option("--input", exists=True, file_okay=False)],
    config: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Kirish papkasini inventarizatsiya qiladi va resume bazasiga saqlaydi."""

    configure_logging()
    settings = load_settings(config)
    settings.prepare_directories()
    files, summary = discover_files(input_path)
    store = StateStore(settings.app.database_path)
    store.initialize()
    store.save_scan(files, summary)
    typer.echo(json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command()
def selftest(
    config: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Tashqi dasturlar mavjudligini tekshiradi."""

    settings = load_settings(config)
    checks = check_tools(settings)
    for check in checks:
        marker = "OK" if check.available else "YO'Q"
        typer.echo(f"[{marker}] {check.name}: {check.path or check.install_hint}")


@app.command()
def web(
    host: Annotated[str | None, typer.Option()] = None,
    port: Annotated[int | None, typer.Option(min=1024, max=65535)] = None,
    config: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Faqat lokal manzilda web boshqaruv panelini ishga tushiradi."""

    settings = load_settings(config)
    resolved_host = host or settings.web.host
    if resolved_host not in {"127.0.0.1", "localhost", "::1"}:
        raise typer.BadParameter("Maxfiylik uchun web server faqat localhost'da ishlaydi")
    uvicorn.run("bankxat.web:app", host=resolved_host, port=port or settings.web.port)


if __name__ == "__main__":
    app()
