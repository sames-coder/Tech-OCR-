from pathlib import Path

from fastapi.testclient import TestClient

from bankxat.config import AppConfig, Settings
from bankxat.web import create_app


def test_upload_flow(tmp_path: Path) -> None:
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data" / "state.sqlite",
        ),
        uploads={"directory": tmp_path / "uploads"},
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/uploads",
            files=[
                ("files", ("xat.pdf", b"soxta-pdf", "application/pdf")),
                ("files", ("rasm.png", b"soxta-rasm", "image/png")),
            ],
        )

        assert response.status_code == 200
        assert response.json()["uploaded_files"] == 2
        assert response.json()["unique_files"] == 2
        uploaded = tmp_path / "uploads" / response.json()["batch_id"] / "xat.pdf"
        assert uploaded.exists()


def test_local_security_headers_and_review_api(tmp_path: Path) -> None:
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data/state.sqlite",
        ),
        uploads={"directory": tmp_path / "uploads"},
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/review")

        assert response.status_code == 200
        assert response.json() == []
        assert response.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_ai_status_reports_disabled_without_network_call(tmp_path: Path) -> None:
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data/state.sqlite",
        ),
        uploads={"directory": tmp_path / "uploads"},
        ai={"enabled": False},
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/ai-status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "available": False,
        "model": "qwen3:1.7b",
    }


def test_folder_upload_preserves_relative_paths(tmp_path: Path) -> None:
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data" / "state.sqlite",
        ),
        uploads={"directory": tmp_path / "uploads"},
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/uploads",
            files=[("files", ("xat.pdf", b"soxta-pdf", "application/pdf"))],
            data={"relative_paths": "sentabr/bank/xat.pdf"},
        )

        assert response.status_code == 200
        uploaded = tmp_path / "uploads" / response.json()["batch_id"] / "sentabr/bank/xat.pdf"
        assert uploaded.exists()


def test_upload_rejects_unsafe_filename(tmp_path: Path) -> None:
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data" / "state.sqlite",
        ),
        uploads={"directory": tmp_path / "uploads"},
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/uploads",
            files={"files": ("..", b"x", "application/octet-stream")},
        )

        assert response.status_code == 422


def test_clear_workspace_removes_runtime_data_but_keeps_original(tmp_path: Path) -> None:
    original = tmp_path / "original.txt"
    original.write_text(
        "4111111111111111 kartasidan 4012888888881881 kartasiga o'tkazildi",
        encoding="utf-8",
    )
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data" / "state.sqlite",
        ),
        uploads={"directory": tmp_path / "uploads"},
    )

    with TestClient(create_app(settings)) as client:
        upload = client.post(
            "/api/uploads",
            files={"files": ("xat.txt", original.read_bytes(), "text/plain")},
        )
        assert upload.status_code == 200
        assert (tmp_path / "output/results.json").exists()

        cleared = client.request(
            "DELETE",
            "/api/workspace",
            json={"confirm": "CLEAR_ALL"},
        )

        assert cleared.status_code == 200
        assert cleared.json() == {"cleared": True}
        assert original.exists()
        assert not (tmp_path / "output/results.json").exists()
        assert list((tmp_path / "uploads").iterdir()) == []
        assert client.get("/api/dashboard").json()["runs"] == 0
        assert client.get("/api/results").json() == []


def test_clear_workspace_requires_explicit_confirmation(tmp_path: Path) -> None:
    settings = Settings(
        app=AppConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
            database_path=tmp_path / "data/state.sqlite",
        ),
        uploads={"directory": tmp_path / "uploads"},
    )

    with TestClient(create_app(settings)) as client:
        response = client.request(
            "DELETE",
            "/api/workspace",
            json={"confirm": "NOT_CONFIRMED"},
        )

        assert response.status_code == 422
