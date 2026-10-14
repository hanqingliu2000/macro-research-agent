from __future__ import annotations

import io
import json
from pathlib import Path

import httpx
import pytest
from macro_research_agent.app import create_app
from macro_research_agent.config import Settings
from openpyxl import Workbook
from test_workflow_persistence import session_document


async def _client_with_session(tmp_path: Path) -> httpx.AsyncClient:
    app = create_app(Settings(environment="test", runtime_dir=tmp_path, llm_provider="test"))
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    await client.post("/api/v1/workflow/sessions", json={"session": session_document()})
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content", "expected_columns"),
    [
        ("macro.csv", b"country,year,secret_value\nUSA,2024,9.75\n", 3),
        (
            "macro.json",
            json.dumps([{"country": "USA", "year": 2024, "secret_value": 9.75}]).encode(),
            3,
        ),
    ],
)
async def test_upload_returns_schema_without_raw_values(
    tmp_path: Path, filename: str, content: bytes, expected_columns: int
) -> None:
    client = await _client_with_session(tmp_path)
    response = await client.post(
        "/api/v1/workflow/sessions/workflow-test-1/sources/uploads",
        files={"file": (filename, content)},
    )
    trace = await client.get("/api/v1/admin/workflow/sessions/workflow-test-1/trace")
    await client.aclose()

    assert response.status_code == 201
    body = response.json()
    assert body["tables"][0]["column_count"] == expected_columns
    assert body["tables"][0]["columns"][2]["inferred_type"] == "number"
    assert "9.75" not in response.text
    assert "9.75" not in trace.text
    stored = tmp_path / "workflow" / "sessions" / "workflow-test-1" / "uploads"
    assert next(stored.glob("upload-*/source.*")).read_bytes() == content


@pytest.mark.asyncio
async def test_xlsx_upload_lists_sheets_and_columns_only(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Quarterly"
    sheet.append(["entity", "period", "value"])
    sheet.append(["JPN", "2024-Q1", 123.45])
    buffer = io.BytesIO()
    workbook.save(buffer)
    client = await _client_with_session(tmp_path)
    response = await client.post(
        "/api/v1/workflow/sessions/workflow-test-1/sources/uploads",
        files={
            "file": (
                "../unsafe.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    await client.aclose()

    assert response.status_code == 201
    assert response.json()["filename"] == "unsafe.xlsx"
    assert response.json()["tables"][0]["name"] == "Quarterly"
    assert "123.45" not in response.text


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_files(tmp_path: Path) -> None:
    client = await _client_with_session(tmp_path)
    response = await client.post(
        "/api/v1/workflow/sessions/workflow-test-1/sources/uploads",
        files={"file": ("notes.txt", b"not data")},
    )
    await client.aclose()
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_malformed_xlsx_as_validation_error(tmp_path: Path) -> None:
    client = await _client_with_session(tmp_path)
    response = await client.post(
        "/api/v1/workflow/sessions/workflow-test-1/sources/uploads",
        files={"file": ("fake.xlsx", b"not-a-zip-workbook")},
    )
    await client.aclose()
    assert response.status_code == 422
    assert response.json()["detail"] == "XLSX content could not be parsed."
