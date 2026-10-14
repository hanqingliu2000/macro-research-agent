from __future__ import annotations

from dataclasses import dataclass

from macro_research_agent.workflow.graph.contracts import (
    GraphEdgeKind,
    GraphSnapshot,
    NodeLifecycle,
    ResearchNodeKind,
)
from macro_research_agent.workflow.states import SessionState, WorkflowStage


@dataclass(frozen=True)
class WorkflowProjectionFacts:
    status: SessionState
    active_stage: WorkflowStage
    reachable_stages: list[WorkflowStage]
    current_snapshot_refs: dict[str, str | None]
    review_requirements: list[str]
    used_legacy_fallback: bool = False


class WorkflowProjectionError(ValueError):
    pass


class WorkflowProjectionService:
    """Derive the public Workflow cursor from current graph state."""

    @staticmethod
    def derive(
        snapshot: GraphSnapshot,
        *,
        fallback_status: SessionState,
        fallback_stage: WorkflowStage,
        fallback_reachable: list[WorkflowStage],
    ) -> WorkflowProjectionFacts:
        superseded = {
            edge.target_node_id
            for edge in snapshot.edges
            if edge.kind == GraphEdgeKind.SUPERSEDES and edge.target_node_id is not None
        }
        current_nodes = [
            node
            for node in snapshot.nodes
            if node.lifecycle != NodeLifecycle.STALE and node.node_id not in superseded
        ]

        def has(kinds: set[ResearchNodeKind], states: set[NodeLifecycle] | None = None) -> bool:
            return any(
                node.kind in kinds and (states is None or node.lifecycle in states)
                for node in current_nodes
            )

        if not current_nodes:
            raise WorkflowProjectionError(
                "Workflow graph has no current node; legacy cursor fallback is retired."
            )

        status = SessionState.CLARIFYING
        completed = {NodeLifecycle.COMPLETED, NodeLifecycle.APPROVED}
        active = {NodeLifecycle.PENDING, NodeLifecycle.READY, NodeLifecycle.IN_PROGRESS}
        if has(set(ResearchNodeKind), {NodeLifecycle.FAILED}):
            status = SessionState.FAILED
        elif has(set(ResearchNodeKind), {NodeLifecycle.CANCELLED}):
            status = SessionState.CANCELLED
        elif has({ResearchNodeKind.REPRODUCTION_MANIFEST}, {NodeLifecycle.COMPLETED}):
            status = SessionState.COMPLETED
        elif has({ResearchNodeKind.OUTPUT_GENERATION}, {NodeLifecycle.IN_PROGRESS}):
            status = SessionState.OUTPUT_GENERATING
        elif has(
            {
                ResearchNodeKind.OUTPUT_GENERATION,
                ResearchNodeKind.OUTPUT_REVISION,
                ResearchNodeKind.OUTPUT_COMPLIANCE_REVIEW,
                ResearchNodeKind.VISUAL_ARTIFACT_REVIEW,
                ResearchNodeKind.SEMANTIC_REPORT_REVIEW,
            },
            completed | {NodeLifecycle.WAITING_FOR_REVIEW},
        ):
            status = SessionState.OUTPUT_REVIEW
        elif has(
            {ResearchNodeKind.TRANSFORMATION_PIPELINE, ResearchNodeKind.MODEL_EXECUTION},
            {NodeLifecycle.IN_PROGRESS},
        ):
            status = SessionState.PIPELINE_RUNNING
        elif has({ResearchNodeKind.DATA_PREPARATION}, {NodeLifecycle.APPROVED}):
            status = SessionState.PIPELINE_EDITING
        elif has(
            {ResearchNodeKind.DATA_ACQUISITION, ResearchNodeKind.DATA_MERGE},
            {NodeLifecycle.IN_PROGRESS},
        ):
            status = SessionState.ACQUIRING
        elif has(
            {
                ResearchNodeKind.DATA_ACQUISITION,
                ResearchNodeKind.DATA_MERGE,
                ResearchNodeKind.DATA_PREPARATION,
            },
            completed | {NodeLifecycle.WAITING_FOR_REVIEW},
        ):
            status = SessionState.DATA_REVIEW
        elif has({ResearchNodeKind.RESEARCH_PLAN}, {NodeLifecycle.APPROVED}):
            status = SessionState.ACQUIRING
        elif has(
            {ResearchNodeKind.RESEARCH_PLAN},
            completed | {NodeLifecycle.WAITING_FOR_REVIEW},
        ):
            status = SessionState.PLAN_REVIEW
        elif has({ResearchNodeKind.CLARIFICATION_BATCH}, active):
            status = SessionState.CLARIFYING

        stage_for_status = {
            SessionState.CLARIFYING: WorkflowStage.PLAN,
            SessionState.PLAN_REVIEW: WorkflowStage.PLAN,
            SessionState.ACQUIRING: WorkflowStage.DATA,
            SessionState.DATA_REVIEW: WorkflowStage.DATA,
            SessionState.PIPELINE_EDITING: WorkflowStage.TRANSFORMATION,
            SessionState.PIPELINE_RUNNING: WorkflowStage.TRANSFORMATION,
            SessionState.OUTPUT_GENERATING: WorkflowStage.OUTPUT,
            SessionState.OUTPUT_REVIEW: WorkflowStage.OUTPUT,
            SessionState.COMPLETED: WorkflowStage.OUTPUT,
        }
        active_stage = stage_for_status.get(status)
        used_legacy_fallback = False
        if active_stage is None:
            terminal_nodes = [
                node
                for node in current_nodes
                if node.lifecycle in {NodeLifecycle.FAILED, NodeLifecycle.CANCELLED}
            ]
            latest_terminal = max(terminal_nodes, key=lambda node: node.updated_at)
            if latest_terminal.stage is None:
                active_stage = fallback_stage
                used_legacy_fallback = True
            else:
                active_stage = latest_terminal.stage

        reachable: list[WorkflowStage] = [WorkflowStage.PLAN]
        data_reached = active_stage != WorkflowStage.PLAN or has(
            {
                ResearchNodeKind.DATA_ACQUISITION,
                ResearchNodeKind.DATA_MERGE,
                ResearchNodeKind.DATA_PREPARATION,
            }
        )
        transformation_reached = active_stage in {
            WorkflowStage.TRANSFORMATION,
            WorkflowStage.OUTPUT,
        } or has({ResearchNodeKind.TRANSFORMATION_PIPELINE, ResearchNodeKind.MODEL_EXECUTION})
        output_reached = active_stage == WorkflowStage.OUTPUT or has(
            {
                ResearchNodeKind.OUTPUT_GENERATION,
                ResearchNodeKind.OUTPUT_REVISION,
                ResearchNodeKind.OUTPUT_COMPLIANCE_REVIEW,
                ResearchNodeKind.VISUAL_ARTIFACT_REVIEW,
                ResearchNodeKind.SEMANTIC_REPORT_REVIEW,
                ResearchNodeKind.REPRODUCTION_MANIFEST,
            }
        )
        if data_reached:
            reachable.append(WorkflowStage.DATA)
        if transformation_reached:
            reachable.append(WorkflowStage.TRANSFORMATION)
        if output_reached:
            reachable.append(WorkflowStage.OUTPUT)
        if active_stage not in reachable:
            reachable = list(dict.fromkeys([*fallback_reachable, active_stage]))

        refs: dict[str, str | None] = {
            "plan": None,
            "data": None,
            "analytical_bundle": None,
            "artifact": None,
        }
        refs.update({pointer.role: pointer.ref_id for pointer in snapshot.active_pointers})
        review_requirements = {
            SessionState.CLARIFYING: ["clarification"],
            SessionState.PLAN_REVIEW: ["research_plan"],
            SessionState.PIPELINE_EDITING: ["pipeline_execution"],
            SessionState.OUTPUT_REVIEW: ["final_outputs"],
        }.get(status, [])
        return WorkflowProjectionFacts(
            status=status,
            active_stage=active_stage,
            reachable_stages=reachable,
            current_snapshot_refs=refs,
            review_requirements=review_requirements,
            used_legacy_fallback=used_legacy_fallback,
        )
