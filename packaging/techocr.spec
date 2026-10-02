"""PyInstaller build tavsifi. Faqat Windows runner ichida ishlatiladi."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).parent
vendor_root = project_root / "packaging" / "vendor"

datas = [
    (str(project_root / "src" / "bankxat" / "static"), "bankxat/static"),
    (str(project_root / "config" / "default.toml"), "config"),
    (str(project_root / "config" / "keywords.toml"), "config"),
]
if (vendor_root / "7zip").exists():
    datas.append((str(vendor_root / "7zip"), "tools/7zip"))
if (vendor_root / "tesseract").exists():
    datas.append((str(vendor_root / "tesseract"), "tools/tesseract"))

analysis = Analysis(
    [str(project_root / "packaging" / "windows_launcher.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("uvicorn"),
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="TechOCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
)
collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="TechOCR",
)
