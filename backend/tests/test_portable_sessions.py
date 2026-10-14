from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from test_workflow_persistence import session_document


@pytest.mark.asyncio
async def test_portable_export_import_restores_files_with_new_identity(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        source = session_document("portable-source")
        created = await client.post("/api/v1/workflow/sessions", json={"session": source})
        assert created.status_code == 201
        uploaded = await client.post(
            "/api/v1/workflow/sessions/portable-source/sources/uploads",
            files={"file": ("input.csv", b"country,value\nUSA,1\n", "text/csv")},
        )
        assert uploaded.status_code == 201
        owned_file = tmp_path / "workflow/sessions/portable-source/data/example.txt"
        owned_file.parent.mkdir(parents=True)
        owned_file.write_text("portable payload", encoding="utf-8")

        exported = await client.get("/api/v1/workflow/sessions/portable-source/archive")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith(
            "application/vnd.macro-research-session+zip"
        )
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            assert {"manifest.json", "database.json", "files/data/example.txt"}.issubset(
                archive.namelist()
            )

        imported = await client.post(
            "/api/v1/workflow/sessions/import",
            files={"file": ("research.mra.zip", exported.content, "application/zip")},
        )
        assert imported.status_code == 201, imported.text
        imported_session = imported.json()["session"]
        assert imported_session["id"] != "portable-source"
        assert imported_session["lineage"]["relationship"] == "import"
        assert imported_session["lineage"]["sourceSessionId"] == "portable-source"
        restored = (
            tmp_path
            / "workflow/sessions"
            / imported_session["id"]
            / "data/example.txt"
        )
        assert restored.read_text(encoding="utf-8") == "portable payload"
        imported_uploads = await client.get(
            f"/api/v1/workflow/sessions/{imported_session['id']}/sources/uploads"
        )
        assert imported_uploads.status_code == 200
        assert imported_uploads.json()[0]["session_id"] == imported_session["id"]
        imported_upload_id = imported_uploads.json()[0]["upload_id"]
        imported_source = (
            tmp_path
            / "workflow/sessions"
            / imported_session["id"]
            / "uploads"
            / imported_upload_id
            / "source.csv"
        )
        assert imported_source.read_text(encoding="utf-8") == "country,value\nUSA,1\n"
        graph = await client.get(
            f"/api/v1/admin/workflow/sessions/{imported_session['id']}/graph"
        )
        assert graph.status_code == 200
        assert graph.json()["session_id"] == imported_session["id"]
        trace = await client.get(
            f"/api/v1/admin/workflow/sessions/{imported_session['id']}/trace"
        )
        assert trace.json()[-1]["event_type"] == "session.imported"


@pytest.mark.asyncio
async def test_import_rejects_checksum_mismatch(tmp_path: Path) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        invalid = io.BytesIO()
        with zipfile.ZipFile(invalid, "w") as archive:
            archive.writestr(
                "manifest.json",
                '{"schema_version":"mra-portable-session-v1","source_session_id":"x",'
                '"source_status":"completed","exported_at":"2026-09-06T00:00:00Z",'
                '"database_checksum":"sha256:bad","files":[]}',
            )
            archive.writestr("database.json", "{}")
        response = await client.post(
            "/api/v1/workflow/sessions/import",
            files={"file": ("invalid.mra.zip", invalid.getvalue(), "application/zip")},
        )
        assert response.status_code == 422
        assert "checksum" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_completed_session_fork_reopens_review_without_mutating_source(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    document = session_document("finished-source")
    document.update(
        {
            "status": "completed",
            "activeStage": "output",
            "reachedStages": ["plan", "data", "transformation", "output"],
            "stageHealth": {
                "plan": "completed",
                "data": "completed",
                "transformation": "completed",
                "output": "completed",
            },
            "output": {
                "finalizedAt": "2026-09-06T00:00:00Z",
                "manifestArtifactId": "manifest-1",
                "artifacts": [
                    {
                        "id": "chart-1",
                        "kind": "chart",
                        "status": "frozen",
                        "exportSelected": True,
                    },
                    {
                        "id": "manifest-1",
                        "kind": "manifest",
                        "status": "frozen",
                        "exportSelected": True,
                    },
                ],
                "reviewReport": {"status": "pass"},
            },
        }
    )
    document["nodes"] = [
        *document["nodes"],  # type: ignore[index]
        {
            "id": "output-generation-1",
            "kind": "output_generation",
            "status": "completed",
            "inputSnapshotIds": ["bundle-1"],
            "outputSnapshotId": "artifact-set-1",
            "createdAt": "2026-09-06T00:00:00Z",
            "updatedAt": "2026-09-06T00:00:00Z",
        },
        {
            "id": "manifest-node-1",
            "kind": "reproduction_manifest",
            "status": "completed",
            "inputSnapshotIds": ["artifact-set-1"],
            "outputSnapshotId": "manifest-1",
            "createdAt": "2026-09-06T00:00:00Z",
            "updatedAt": "2026-09-06T00:00:00Z",
        },
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/api/v1/workflow/sessions", json={"session": document})
        assert created.status_code == 201, created.text
        forked = await client.post(
            "/api/v1/workflow/sessions/finished-source/fork",
            json={"title": "Continued analysis"},
        )
        assert forked.status_code == 201, forked.text
        child = forked.json()
        assert child["session"]["title"] == "Continued analysis"
        assert child["session"]["status"] == "output_review"
        assert child["projection"]["status"] == "output_review"
        assert child["session"]["output"].get("finalizedAt") is None
        assert child["session"]["output"].get("reviewReport") is None
        assert [item["id"] for item in child["session"]["output"]["artifacts"]] == [
            "chart-1"
        ]
        original = await client.get("/api/v1/workflow/sessions/finished-source")
        assert original.json()["session"]["status"] == "completed"
        assert original.json()["session"]["output"]["manifestArtifactId"] == "manifest-1"
