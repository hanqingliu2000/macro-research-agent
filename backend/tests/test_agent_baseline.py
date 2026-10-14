from macro_research_agent.trace.writer import redact_trace_value
from macro_research_agent.workflow.code_workspace import _stata_model
from macro_research_agent.workflow.planning_service import _upsert_node


def test_plan_revision_never_rewrites_completed_references() -> None:
    old = {
        "id": "node-old",
        "kind": "research_plan",
        "status": "completed",
        "outputSnapshotId": "old",
        "inputSnapshotIds": [],
    }
    session = {"nodes": [old]}
    _upsert_node(session, "research_plan", "waiting_for_review", output_snapshot_id="new")
    assert old["outputSnapshotId"] == "old" and old["status"] == "stale"
    assert session["nodes"][-1]["supersedesNodeId"] == "node-old"
    assert session["nodes"][-1]["outputSnapshotId"] == "new"


def test_credentials_and_hidden_reasoning_are_redacted_inside_text() -> None:
    raw = {
        "message": "Bearer token123 api_key=abc123 sk-thisisatestkey123 <think>private</think>",
        "reasoning_content": "private",
        "nested": [{"password": "abc"}],
    }
    safe = str(redact_trace_value(raw))
    for secret in ("token123", "abc123", "sk-thisisatestkey123", "private"):
        assert secret not in safe
    assert "[REDACTED]" in safe


def test_stata_dotted_indicator_names_have_stable_safe_mapping() -> None:
    lines = _stata_model(
        {"kind": "descriptive", "variables": ["NY.GDP.MKTP.KD.ZG"], "parameters": {}}, "active", 1
    )
    assert any('if indicator_code == "NY.GDP.MKTP.KD.ZG"' in line for line in lines)
    assert any("replace indicator_code" in line for line in lines)
