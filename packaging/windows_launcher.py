"""Windows distributivi uchun Tech OCR ishga tushirgichi."""

from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from bankxat.config import load_settings


def resource_root() -> Path:
    """PyInstaller ichidagi yoki source checkout'dagi resurs katalogini qaytaradi."""

    frozen_root = getattr(sys, "_MEIPASS", None)
    return Path(frozen_root) if frozen_root else Path(__file__).resolve().parents[1]


def local_data_root() -> Path:
    """Yozish mumkin bo'lgan foydalanuvchi katalogini tanlaydi."""

    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    target = base / "TechOCR"
    target.mkdir(parents=True, exist_ok=True)
    return target


def port_is_open(host: str, port: int) -> bool:
    """Ilovaning boshqa nusxasi portni band qilganini tekshiradi."""

    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def main() -> None:
    """Lokal yo'llarni sozlab, server va brauzerni ishga tushiradi."""

    resources = resource_root()
    data_root = local_data_root()
    os.chdir(data_root)

    settings = load_settings(resources / "config" / "default.toml")
    settings.app.data_dir = data_root / "data"
    settings.app.output_dir = data_root / "output"
    settings.app.database_path = data_root / "data" / "state.sqlite"
    settings.uploads.directory = data_root / "data" / "uploads"

    seven_zip = resources / "tools" / "7zip" / "7z.exe"
    tesseract = resources / "tools" / "tesseract" / "tesseract.exe"
    libreoffice = (
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
        / "LibreOffice"
        / "program"
        / "soffice.exe"
    )
    if seven_zip.exists():
        settings.archives.seven_zip_path = str(seven_zip)
    if tesseract.exists():
        settings.ocr.tesseract_path = str(tesseract)
        os.environ["TESSDATA_PREFIX"] = str(tesseract.parent / "tessdata")
    if libreoffice.exists():
        settings.ocr.libreoffice_path = str(libreoffice)

    host = settings.web.host
    port = settings.web.port
    address = f"http://{host}:{port}/"
    if port_is_open(host, port):
        webbrowser.open(address)
        return

    # Importdan oldin ish katalogi foydalanuvchi katalogiga ko'chiriladi.
    from bankxat.web import create_app

    application = create_app(settings)
    threading.Timer(1.2, lambda: webbrowser.open(address)).start()
    uvicorn.run(application, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
