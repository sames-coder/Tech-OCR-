"""Lokal boshqaruv paneli va API."""

import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, cast
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bankxat import __version__
from bankxat.config import Settings, load_settings
from bankxat.discovery import discover_files
from bankxat.output import (
    clear_generated_files,
    public_results,
    public_review_items,
    review_count,
)
from bankxat.processor import process_directory
from bankxat.selftest import checks_as_dicts
from bankxat.semantic import assistant_status
from bankxat.store import StateStore

STATIC_DIR = Path(__file__).parent / "static"


class ClearWorkspaceRequest(BaseModel):
    """Tasodifiy yoki noto'g'ri tozalash so'rovini bloklovchi tasdiq modeli."""

    confirm: Literal["CLEAR_ALL"]


def safe_upload_name(raw_name: str) -> str:
    """Brauzer yuborgan nomdan katalog qismlarini olib tashlaydi."""

    normalized = raw_name.replace("\\", "/")
    name = normalized.rsplit("/", maxsplit=1)[-1].strip()
    if not name or name in {".", ".."} or "\x00" in name:
        raise ValueError("Fayl nomi yaroqsiz")
    return name


def safe_relative_upload_path(raw_path: str) -> Path:
    """Papka tanlovidagi nisbiy yo'lni traversal hujumlaridan tozalaydi."""

    normalized = raw_path.replace("\\", "/").strip()
    candidate = PurePosixPath(normalized)
    if (
        not normalized
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or "\x00" in normalized
    ):
        raise ValueError("Faylning papka yo'li yaroqsiz")
    return Path(*candidate.parts)


async def save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    """Yuklamani chegaralangan bo'laklarda atomik tarzda diskka yozadi."""

    temporary = destination.with_suffix(f"{destination.suffix}.part")
    written = 0
    try:
        with temporary.open("xb") as stream:
            while chunk := await upload.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"{destination.name} fayli ruxsat etilgan hajmdan katta",
                    )
                stream.write(chunk)
        temporary.chmod(0o600)
        temporary.replace(destination)
        return written
    finally:
        await upload.close()
        if temporary.exists():
            temporary.unlink()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Testlarda alohida sozlama bilan yaratiladigan ilova fabrikasi."""

    active_settings = settings or load_settings()
    active_settings.prepare_directories()
    store = StateStore(active_settings.app.database_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        store.initialize()
        yield

    app = FastAPI(
        title="Tech OCR",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.store = store
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.middleware("http")
    async def local_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Lokal UI javoblarini cache va tashqi resurslardan himoyalaydi."""

        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    def get_store() -> StateStore:
        return cast(StateStore, app.state.store)

    StoreDependency = Annotated[StateStore, Depends(get_store)]

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "mode": "local-only"}

    @app.get("/api/dashboard")
    def dashboard(state: StoreDependency) -> dict[str, object]:
        data = state.dashboard()
        data["pending_review"] = review_count(active_settings.app.output_dir)
        return data

    @app.get("/api/files")
    def files(state: StoreDependency) -> list[dict[str, object]]:
        return state.recent_files()

    @app.get("/api/results")
    def results() -> list[dict[str, object]]:
        return public_results(active_settings.app.output_dir)

    @app.get("/api/review")
    def review_items() -> list[dict[str, object]]:
        return public_review_items(active_settings.app.output_dir)

    @app.get("/api/selftest")
    def selftest() -> list[dict[str, object]]:
        return checks_as_dicts(active_settings)

    @app.get("/api/ai-status")
    def ai_status() -> dict[str, object]:
        return assistant_status(active_settings.ai)

    @app.delete("/api/workspace")
    def clear_workspace(request: ClearWorkspaceRequest, state: StoreDependency) -> dict[str, bool]:
        state.clear_processing_data()
        clear_generated_files(
            active_settings.app.output_dir,
            active_settings.uploads.directory,
        )
        return {"cleared": True}

    @app.post("/api/uploads")
    async def upload_files(
        state: StoreDependency,
        files: Annotated[list[UploadFile], File(description="Lokal hujjatlar")],
        relative_paths: Annotated[list[str] | None, Form()] = None,
    ) -> dict[str, object]:
        if not files:
            raise HTTPException(status_code=422, detail="Kamida bitta fayl tanlang")
        if len(files) > active_settings.uploads.max_files_per_batch:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Bir urinishda ko'pi bilan "
                    f"{active_settings.uploads.max_files_per_batch} ta fayl yuklash mumkin"
                ),
            )

        if relative_paths is not None and len(relative_paths) != len(files):
            raise HTTPException(status_code=422, detail="Fayl yo'llari soni mos emas")

        batch_id = uuid4().hex
        batch_directory = active_settings.uploads.directory / batch_id
        batch_directory.mkdir(parents=True, mode=0o700)
        used_paths: set[Path] = set()

        try:
            for index, upload in enumerate(files):
                try:
                    raw_path = (
                        relative_paths[index]
                        if relative_paths is not None
                        else safe_upload_name(upload.filename or "")
                    )
                    relative_path = safe_relative_upload_path(raw_path)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                if relative_path in used_paths:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Takroriy fayl yo'li: {relative_path}",
                    )
                used_paths.add(relative_path)
                destination = batch_directory / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                await save_upload(
                    upload,
                    destination,
                    active_settings.uploads.max_file_bytes,
                )

            discovered, summary = discover_files(batch_directory)
            state.save_scan(discovered, summary)
            _, processing_stats = process_directory(batch_directory, active_settings)
        except Exception:
            shutil.rmtree(batch_directory)
            raise

        response = summary.model_dump(mode="json")
        response["uploaded_files"] = len(files)
        response["batch_id"] = batch_id
        response["processing"] = processing_stats
        return response

    return app


app = create_app()
