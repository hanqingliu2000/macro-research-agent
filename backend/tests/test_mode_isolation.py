from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "macro_research_agent"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def assert_package_does_not_import(package: str, forbidden: str) -> None:
    forbidden_prefix = f"macro_research_agent.{forbidden}"
    violations: list[str] = []
    for path in (PACKAGE_ROOT / package).rglob("*.py"):
        matched = sorted(
            module
            for module in imported_modules(path)
            if module == forbidden_prefix or module.startswith(f"{forbidden_prefix}.")
        )
        if matched:
            violations.append(f"{path.name}: {', '.join(matched)}")
    assert not violations, "; ".join(violations)


def test_agent_does_not_import_workflow() -> None:
    assert_package_does_not_import("agent", "workflow")


def test_workflow_does_not_import_agent() -> None:
    assert_package_does_not_import("workflow", "agent")


def test_stage_mutations_commit_only_through_graph_service() -> None:
    stage_files = [
        PACKAGE_ROOT / "workflow" / "planning_service.py",
        PACKAGE_ROOT / "workflow" / "data_service.py",
        PACKAGE_ROOT / "workflow" / "pipeline_service.py",
        PACKAGE_ROOT / "workflow" / "output_service.py",
    ]
    for path in stage_files:
        source = path.read_text(encoding="utf-8")
        assert "graph_service.apply_transition(" in source, path.name
        assert "repository.dispatch(" not in source, path.name
        assert "repository.commit_graph_transition(" not in source, path.name

    routes = (PACKAGE_ROOT / "api" / "workflow_routes.py").read_text(encoding="utf-8")
    assert '"/sessions/{session_id}/commands"' not in routes
    assert "repository.commit_graph_transition(" not in routes
