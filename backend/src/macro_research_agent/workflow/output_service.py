from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from macro_research_agent.trace.events import Actor
from macro_research_agent.workflow.api_schemas import (
    WorkflowCommandMeta,
    WorkflowCommandResponse,
    WorkflowSessionDocument,
)
from macro_research_agent.workflow.graph.service import GraphService
from macro_research_agent.workflow.handoff import (
    AgentRuntimeDescriptor,
    append_stage_message,
    record_stage_handoff,
)
from macro_research_agent.workflow.model_data_access import WorkflowModelDataAccessService
from macro_research_agent.workflow.output_review import (
    ArtifactAuthorPort,
    OutputReviewPort,
    OutputReviewRequest,
    deterministic_preflight,
    incomplete_patch_groups,
    output_artifact_set_hash,
    selected_preflight_findings,
    stable_hash,
)
from macro_research_agent.workflow.output_workspace import (
    OutputWorkspaceError,
    OutputWorkspaceManager,
)
from macro_research_agent.workflow.ports import WorkflowRepository
from macro_research_agent.workflow.publication_guidelines import PUBLICATION_GUIDELINE
from macro_research_agent.workflow.reporting import ReportRevisionDirectiveV1
from macro_research_agent.workflow.states import SessionState, WorkflowStage

MAX_OUTPUT_REVIEW_ITERATIONS = 3
OUTPUT_REVISION_FORMATS = frozenset({"svg", "csv", "xlsx"})


class WorkflowOutputService:
    allowed_commands = {
        "select_artifact",
        "toggle_artifact_export",
        "request_output_review",
        "propose_output_revision",
        "apply_output_revision",
        "reject_output_revision",
        "finalize_output",
    }
    owned_commands = allowed_commands

    def __init__(
        self,
        repository: WorkflowRepository,
        graph_service: GraphService,
        manager: OutputWorkspaceManager,
        artifact_author: ArtifactAuthorPort,
        output_reviewer: OutputReviewPort,
        model_data_access: WorkflowModelDataAccessService,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.manager = manager
        self.artifact_author = artifact_author
        self.output_reviewer = output_reviewer
        self.model_data_access = model_data_access

    def _dispatch(
        self,
        meta: WorkflowCommandMeta,
        command: dict[str, Any],
        session: dict[str, Any],
    ) -> WorkflowCommandResponse:
        return self.graph_service.apply_transition(
            meta, command, WorkflowSessionDocument.model_validate(session)
        )

    def execute(
        self, meta: WorkflowCommandMeta, command: dict[str, Any]
    ) -> WorkflowCommandResponse:
        replay = self.repository.replay_command(meta.session_id, meta.idempotency_key)
        if replay is not None:
            return replay
        command_type = str(command.get("type") or "")
        if command_type not in self.allowed_commands:
            raise OutputWorkspaceError("Command is not allowed in the Output domain.")
        stored = self.repository.require_current(meta)
        session = stored.session.model_dump(mode="json", by_alias=True)
        if session.get("activeStage") != "output":
            raise OutputWorkspaceError("Output commands require the Output stage.")
        output = dict(session.get("output") or {})
        artifacts = list(output.get("artifacts") or [])
        artifact_id = str(command.get("artifactId") or "")

        if stored.session.status == SessionState.COMPLETED:
            raise OutputWorkspaceError(
                "Completed Workflow sessions are read-only. "
                "Continue or fork the session to revise it."
            )
        if (
            command_type
            in {
                "apply_output_revision",
                "reject_output_revision",
                "finalize_output",
            }
            and meta.actor != "user"
        ):
            raise OutputWorkspaceError(
                "Only a user may approve/reject Output revisions or Finish the session."
            )

        if command_type == "select_artifact":
            if artifact_id not in {str(item.get("id")) for item in artifacts}:
                raise OutputWorkspaceError("Unknown output artifact.")
            output["selectedArtifactId"] = artifact_id
        elif command_type == "toggle_artifact_export":
            found = False
            for artifact in artifacts:
                if artifact.get("id") == artifact_id:
                    if artifact.get("status") != "ready":
                        raise OutputWorkspaceError("Only ready artifacts may be selected.")
                    artifact["exportSelected"] = not artifact.get("exportSelected", True)
                    found = True
            if not found:
                raise OutputWorkspaceError("Unknown output artifact.")
            output["artifacts"] = artifacts
            if output.get("reviewReport"):
                output["reviewHistory"] = [
                    *list(output.get("reviewHistory") or []),
                    output["reviewReport"],
                ]
                output.pop("reviewReport", None)
            if output.get("pendingProposal"):
                self._close_proposal_node(
                    session, str(output["pendingProposal"].get("id")), applied=False
                )
                output.pop("pendingProposal", None)
        elif command_type == "request_output_review":
            output = self._run_review(meta.session_id, session, output)
            session["output"] = output
            self._append_review_node(session, output)
            if output.get("pendingProposal"):
                self._append_proposal_node(session, str(output["pendingProposal"]["id"]), output)
            self.repository.record_trace_event(
                meta.session_id,
                "ai.output_review_completed"
                if output.get("reviewReport")
                else "ai.chart_handoff_blocked",
                Actor.AGENT,
                {
                    "provider_profile": self.output_reviewer.provider_profile,
                    "model_id": self.output_reviewer.model_id,
                    "remote_disclosure": self.output_reviewer.remote_data_disclosure,
                    "report_id": (output.get("reviewReport") or {}).get("id"),
                    "target_artifact_set_hash": output.get("artifactSetHash"),
                },
            )
        elif command_type == "propose_output_revision":
            if int(output.get("reviewIteration") or 0) >= MAX_OUTPUT_REVIEW_ITERATIONS:
                raise OutputWorkspaceError("The bounded Output review iteration limit was reached.")
            request = str(command.get("request") or "").strip()
            selected = next(
                (item for item in artifacts if item.get("id") == output.get("selectedArtifactId")),
                next(
                    (item for item in artifacts if item.get("format") in OUTPUT_REVISION_FORMATS),
                    None,
                ),
            )
            if selected is None:
                raise OutputWorkspaceError("No current artifact is available for revision.")
            if selected.get("format") not in OUTPUT_REVISION_FORMATS:
                raise OutputWorkspaceError(
                    "Output revisions are limited to chart and table artifacts."
                )
            specification = dict(
                (output.get("artifactSpecifications") or {}).get(selected.get("id")) or {}
            )
            patches = self.artifact_author.propose_revision(
                request,
                selected,
                specification,
                str(output.get("artifactSetHash") or ""),
            )
            if not patches:
                available_columns = specification.get("columns") or []
                detail = (
                    " Available table columns: "
                    + ", ".join(str(item) for item in available_columns)
                    + "."
                    if available_columns
                    else " Supported changes are title, unit, source note and number format."
                )
                raise OutputWorkspaceError(
                    "The revision request did not name a supported change." + detail
                )
            proposal_id = f"output-proposal-{stable_hash([request, selected.get('id')])[-16:]}"
            output["pendingProposal"] = {
                "id": proposal_id,
                "request": request,
                "summary": f"Revise {selected.get('name')} through its versioned specification.",
                "artifactIds": sorted({item.artifact_id for item in patches}),
                "patches": [
                    {
                        "id": item.patch_id,
                        "groupId": item.group_id,
                        "artifactId": item.artifact_id,
                        "rationale": item.rationale,
                        "changes": item.changes,
                    }
                    for item in patches
                ],
                "targetArtifactSetHash": output.get("artifactSetHash"),
                "targetArtifactHashes": {
                    str(item.get("id")): str(item.get("hash"))
                    for item in artifacts
                    if item.get("id") in {patch.artifact_id for patch in patches}
                },
            }
            self._append_proposal_node(session, proposal_id, output)
        elif command_type == "reject_output_revision":
            pending = dict(output.get("pendingProposal") or {})
            if not pending:
                raise OutputWorkspaceError("There is no pending Output revision proposal.")
            self._close_proposal_node(session, str(pending.get("id")), applied=False)
            output.pop("pendingProposal", None)
        elif command_type == "apply_output_revision":
            pending = dict(output.get("pendingProposal") or {})
            if not pending:
                raise OutputWorkspaceError("There is no pending Output revision proposal.")
            if pending.get("targetArtifactSetHash") != output.get("artifactSetHash"):
                raise OutputWorkspaceError(
                    "The ArtifactSet changed after this proposal was created. "
                    "Request a new proposal."
                )
            current_hashes = {str(item.get("id")): str(item.get("hash")) for item in artifacts}
            if any(
                current_hashes.get(str(key)) != str(value)
                for key, value in dict(pending.get("targetArtifactHashes") or {}).items()
            ):
                raise OutputWorkspaceError(
                    "A targeted artifact changed after this proposal was created."
                )
            if int(output.get("reviewIteration") or 0) >= MAX_OUTPUT_REVIEW_ITERATIONS:
                raise OutputWorkspaceError("The bounded Output review iteration limit was reached.")
            available = {str(item.get("id")) for item in pending.get("patches") or []}
            available_directives = {
                str(item.get("directiveId") or item.get("id"))
                for item in pending.get("reportDirectives") or []
            }
            selected_patch_ids = {
                str(value)
                for value in (
                    (command.get("acceptedPatchIds") or [])
                    if "acceptedPatchIds" in command
                    else available
                )
            }
            selected_directive_ids = {
                str(value)
                for value in (
                    (command.get("acceptedDirectiveIds") or [])
                    if "acceptedDirectiveIds" in command
                    else available_directives
                )
            }
            if (
                (not selected_patch_ids and not selected_directive_ids)
                or not selected_patch_ids.issubset(available)
                or not selected_directive_ids.issubset(available_directives)
            ):
                raise OutputWorkspaceError(
                    "Select at least one valid Output patch or report directive."
                )
            if incomplete_patch_groups(list(pending.get("patches") or []), selected_patch_ids):
                raise OutputWorkspaceError(
                    "Coordinated Output corrections must be applied as a complete group."
                )
            artifacts_by_id = {str(item.get("id")): item for item in artifacts}
            selected_patches = [
                patch
                for patch in pending.get("patches") or []
                if str(patch.get("id")) in selected_patch_ids
            ]
            selected_directives = [
                ReportRevisionDirectiveV1.model_validate(item)
                for item in pending.get("reportDirectives") or []
                if str(item.get("directiveId") or item.get("id")) in selected_directive_ids
            ]
            grouped_directives: dict[str, list[ReportRevisionDirectiveV1]] = {}
            for directive in selected_directives:
                grouped_directives.setdefault(directive.artifact_id, []).append(directive)
            selected_directives = [
                ReportRevisionDirectiveV1(
                    directiveId=(
                        "directive-group-"
                        + stable_hash([item.directive_id for item in directives])[-16:]
                    ),
                    artifactId=artifact_id,
                    targetSectionIds=list(
                        dict.fromkeys(
                            section_id
                            for item in directives
                            for section_id in item.target_section_ids
                        )
                    ),
                    issue="; ".join(item.issue for item in directives),
                    preserveEvidenceRefs=list(
                        dict.fromkeys(
                            ref for item in directives for ref in item.preserve_evidence_refs
                        )
                    ),
                    acceptanceCriteria=list(
                        dict.fromkeys(
                            criterion
                            for item in directives
                            for criterion in item.acceptance_criteria
                        )
                    ),
                )
                for artifact_id, directives in grouped_directives.items()
            ]
            if any(
                (artifacts_by_id.get(str(patch.get("artifactId"))) or {}).get("format")
                not in OUTPUT_REVISION_FORMATS
                for patch in selected_patches
            ):
                raise OutputWorkspaceError(
                    "Output revisions are limited to chart and table artifacts."
                )
            previous_artifact_set_hash = str(output.get("artifactSetHash") or "")
            specifications = dict(output.get("artifactSpecifications") or {})
            previous_artifacts = [
                {
                    **dict(item),
                    "specification": dict(specifications.get(str(item.get("id"))) or {}),
                }
                for item in artifacts
            ]
            render_hashes = dict(output.get("reviewRenderHashes") or {})
            render_refs = dict(output.get("reviewRenderRefs") or {})
            report_drafts = dict(output.get("reportDrafts") or {})
            report_author_requests = dict(output.get("reportAuthorRequests") or {})
            evidence_ledgers = dict(output.get("evidenceLedgers") or {})
            replacements: list[dict[str, Any]] = []
            replacement_ids: dict[str, str] = {}
            for patch in pending.get("patches") or []:
                if str(patch.get("id")) not in selected_patch_ids:
                    continue
                old_id = str(patch.get("artifactId"))
                replacement, specification, render_ref = self.manager.regenerate(
                    meta.session_id,
                    session,
                    old_id,
                    dict(patch.get("changes") or {}),
                )
                replacements.append(
                    {
                        "previousArtifactId": old_id,
                        "artifactId": str(replacement["id"]),
                        "name": str(replacement.get("name") or ""),
                        "format": str(replacement.get("format") or ""),
                        "previousHash": str(artifacts_by_id[old_id].get("hash") or ""),
                        "hash": str(replacement.get("hash") or ""),
                    }
                )
                replacement_ids[old_id] = str(replacement["id"])
                artifacts = [
                    replacement if item.get("id") == old_id else item for item in artifacts
                ]
                specifications.pop(old_id, None)
                specifications[str(replacement["id"])] = specification
                render_hashes.pop(old_id, None)
                render_refs.pop(old_id, None)
                if render_ref is not None:
                    render_hashes[str(replacement["id"])] = str(render_ref["hash"])
                    render_refs[str(replacement["id"])] = render_ref
            if selected_directives:
                session["output"] = {
                    **output,
                    "artifacts": artifacts,
                    "artifactSpecifications": specifications,
                }
            for directive in selected_directives:
                old_id = directive.artifact_id
                old_artifact = artifacts_by_id.get(old_id) or {}
                if old_artifact.get("format") != "report":
                    raise OutputWorkspaceError(
                        "Report directives may revise only a Research Report artifact."
                    )
                replacement, specification, draft, author_request = self.manager.revise_report(
                    meta.session_id,
                    session,
                    old_id,
                    directive,
                )
                replacements.append(
                    {
                        "previousArtifactId": old_id,
                        "artifactId": str(replacement["id"]),
                        "name": str(replacement.get("name") or ""),
                        "format": "report",
                        "previousHash": str(old_artifact.get("hash") or ""),
                        "hash": str(replacement.get("hash") or ""),
                    }
                )
                replacement_ids[old_id] = str(replacement["id"])
                artifacts = [
                    replacement if item.get("id") == old_id else item for item in artifacts
                ]
                specifications.pop(old_id, None)
                specifications[str(replacement["id"])] = specification
                report_drafts.pop(old_id, None)
                report_drafts[str(replacement["id"])] = draft
                report_author_requests.pop(old_id, None)
                report_author_requests[str(replacement["id"])] = author_request
                evidence_ledgers.pop(old_id, None)
                evidence_ledgers[str(replacement["id"])] = list(draft.get("claims") or [])
            replaced_ids = set(replacement_ids)
            unaffected_preflight = [
                item
                for item in output.get("preflightFindings") or []
                if not replaced_ids.intersection(
                    str(value)
                    for value in item.get("artifact_ids") or item.get("artifactIds") or []
                )
            ]
            revised_ids = set(replacement_ids.values())
            final_snapshot_id = str(
                (session.get("pipeline") or {}).get("bundle", {}).get("finalDatasetRef") or ""
            )
            revised_preflight = deterministic_preflight(
                [item for item in artifacts if str(item.get("id")) in revised_ids],
                specifications,
                self.manager.data_manager.get_snapshot(
                    meta.session_id,
                    final_snapshot_id,
                ).row_count,
                {},
                review_render_refs=render_refs,
            )
            output["preflightFindings"] = [
                *unaffected_preflight,
                *(item.model_dump(mode="json") for item in revised_preflight),
            ]
            output["artifactHistory"] = [
                *list(output.get("artifactHistory") or []),
                previous_artifacts,
            ]
            output["artifacts"] = artifacts
            output["artifactSpecifications"] = specifications
            output["reviewRenderHashes"] = render_hashes
            output["reviewRenderRefs"] = render_refs
            output["reportDrafts"] = report_drafts
            output["reportAuthorRequests"] = report_author_requests
            output["evidenceLedgers"] = evidence_ledgers
            if str(output.get("selectedArtifactId") or "") in replacement_ids:
                output["selectedArtifactId"] = replacement_ids[
                    str(output.get("selectedArtifactId"))
                ]
            output["artifactSetHash"] = output_artifact_set_hash(artifacts, specifications)
            applied_at = datetime.now(timezone.utc).isoformat()
            revision_entry = {
                "id": str(pending.get("id") or ""),
                "revision": len(output.get("revisionHistory") or []) + 1,
                "request": str(pending.get("request") or ""),
                "acceptedPatchIds": sorted(selected_patch_ids),
                "acceptedDirectiveIds": sorted(selected_directive_ids),
                "previousArtifactSetHash": previous_artifact_set_hash,
                "artifactSetHash": output["artifactSetHash"],
                "artifacts": replacements,
                "appliedAt": applied_at,
            }
            self._close_proposal_node(session, str(pending.get("id")), applied=True)
            output.pop("pendingProposal", None)
            output = self._run_review(meta.session_id, session, output)
            revision_entry.update(
                {
                    "reviewIteration": int(output.get("reviewIteration") or 0),
                    "reviewReportId": str((output.get("reviewReport") or {}).get("id") or ""),
                    "reviewStatus": str((output.get("reviewReport") or {}).get("status") or "fail"),
                }
            )
            output["revisionHistory"] = [
                *list(output.get("revisionHistory") or []),
                revision_entry,
            ]
            self._append_review_node(session, output)
            if output.get("pendingProposal"):
                self._append_proposal_node(session, str(output["pendingProposal"]["id"]), output)
        else:
            selected_ids = [
                str(item.get("id"))
                for item in artifacts
                if item.get("exportSelected") and item.get("status") == "ready"
            ]
            preflight_failures = [
                item
                for item in selected_preflight_findings(
                    list(output.get("preflightFindings") or []), set(selected_ids)
                )
                if item.severity == "fail" or item.blocking
            ]
            report = dict(output.get("reviewReport") or {})
            if not report:
                raise OutputWorkspaceError("Run Output review before Finish.")
            if preflight_failures or report.get("status") == "fail":
                raise OutputWorkspaceError("Resolve blocking Output review findings before Finish.")
            selected_report = any(
                item.get("format") == "report"
                and item.get("exportSelected")
                and item.get("status") == "ready"
                for item in artifacts
            )
            if selected_report and report.get("semanticReportStatus") != "pass":
                raise OutputWorkspaceError(
                    "The selected Research Report must pass semantic review before Finish."
                )
            if output.get("pendingProposal"):
                raise OutputWorkspaceError(
                    "Apply or reject the pending Output proposal before Finish."
                )
            if report.get("status") == "warning" and not command.get("acceptWarnings"):
                raise OutputWorkspaceError(
                    "Acknowledge the documented Output review warnings before Finish."
                )
            if report.get("targetArtifactSetHash") != output.get("artifactSetHash") or set(
                report.get("reviewedArtifactIds") or []
            ) != set(selected_ids):
                raise OutputWorkspaceError(
                    "The selected ArtifactSet changed after review. Run Output review again."
                )
            manifest = self.manager.finalize_manifest(meta.session_id, session, selected_ids)
            finalized_at = datetime.now(timezone.utc).isoformat()
            for artifact in artifacts:
                if artifact.get("id") in selected_ids:
                    artifact["status"] = "frozen"
            artifacts.append(
                {
                    **self.manager._artifact_payload(manifest),
                    "status": "frozen",
                    "exportSelected": True,
                }
            )
            output.update(
                {
                    "artifacts": artifacts,
                    "manifestArtifactId": manifest.id,
                    "finalizedAt": finalized_at,
                    "selectedArtifactId": manifest.id,
                }
            )
            session["status"] = "completed"
            session["stageHealth"] = {**session.get("stageHealth", {}), "output": "completed"}
            session["lastNotice"] = "Selected artifacts and reproduction manifest are frozen."
            self._update_manifest_node(session, manifest.id, selected_ids, finalized_at)

        session["output"] = output
        session["updatedAt"] = datetime.now(timezone.utc).isoformat()
        return self._dispatch(meta, command, session)

    def _run_review(
        self, session_id: str, session: dict[str, Any], output: dict[str, Any]
    ) -> dict[str, Any]:
        bundle = dict((session.get("pipeline") or {}).get("bundle") or {})
        snapshot_id = str(bundle.get("finalDatasetRef") or "")
        output["maxReviewIterations"] = MAX_OUTPUT_REVIEW_ITERATIONS
        iteration = max(1, int(output.get("reviewIteration") or 0) + 1)
        if iteration > MAX_OUTPUT_REVIEW_ITERATIONS:
            raise OutputWorkspaceError("The bounded Output review iteration limit was reached.")
        if not self._chart_self_checks(session_id, snapshot_id, output):
            return output
        dataset = self.model_data_access.context_for_snapshot(
            session_id,
            snapshot_id,
            WorkflowStage.OUTPUT,
            for_remote_provider=self.output_reviewer.remote_data_disclosure,
            provider_profile=self.output_reviewer.provider_profile,
            model_id=self.output_reviewer.model_id,
        )
        selected = [
            str(item.get("id"))
            for item in output.get("artifacts") or []
            if item.get("exportSelected") and item.get("status") == "ready"
        ]
        request = OutputReviewRequest(
            session_id=session_id,
            artifact_set_id=str(output.get("artifactSetId") or ""),
            artifact_set_hash=str(output.get("artifactSetHash") or ""),
            guideline_version=str(output.get("guidelineVersion") or ""),
            artifacts=list(output.get("artifacts") or []),
            specifications=dict(output.get("artifactSpecifications") or {}),
            review_render_hashes=dict(output.get("reviewRenderHashes") or {}),
            review_render_refs=dict(output.get("reviewRenderRefs") or {}),
            selected_artifact_ids=selected,
            result_summary={
                "bundle_id": bundle.get("id"),
                "diagnostics": bundle.get("diagnostics") or [],
                "warnings": bundle.get("warnings") or [],
                "limitations": output.get("limitations") or [],
            },
            preflight_findings=list(output.get("preflightFindings") or []),
            dataset=dataset,
            iteration=iteration,
            handoff=dict((session.get("handoffs") or [{}])[-1]),
            approved_plan=dict(session.get("currentPlan") or {}),
            model_results=[
                dict(item) for item in (session.get("pipeline") or {}).get("modelResults") or []
            ],
            result_hashes={
                str(item.get("id") or f"result-{index + 1}"): stable_hash(item)
                for index, item in enumerate(
                    (session.get("pipeline") or {}).get("modelResults") or []
                )
            },
            hash_semantics={
                "resultHashes": "hash of each complete typed model-result record",
                "modelResults[].resultHash": (
                    "hash of only the nested numerical result payload; expected to differ "
                    "from resultHashes for the same result ID"
                ),
            },
            report_drafts=dict(output.get("reportDrafts") or {}),
            evidence_ledgers=dict(output.get("evidenceLedgers") or {}),
            publication_guideline=PUBLICATION_GUIDELINE.model_dump(mode="json"),
        )
        self.repository.record_trace_event(
            session_id,
            "ai.model_results_accessed",
            Actor.AGENT,
            {
                "policy_version": "report-evidence-access-v1",
                "operation": "read_model_results",
                "provider_profile": self.output_reviewer.provider_profile,
                "model_id": self.output_reviewer.model_id,
                "result_count": len(request.model_results),
                "result_hash": stable_hash(request.model_results),
            },
        )
        report = self.output_reviewer.review(request, self.model_data_access, self.manager)
        unique_findings = []
        seen_findings: set[tuple[tuple[str, ...], str, str]] = set()
        for item in report.findings:
            key = (tuple(sorted(item.artifact_ids)), item.rule_id, item.message)
            if key not in seen_findings:
                seen_findings.add(key)
                unique_findings.append(item)
        report.findings = unique_findings
        if any(item.severity == "fail" or item.blocking for item in unique_findings):
            report.status = "fail"
        elif unique_findings:
            report.status = "warning"
        else:
            report.status = "pass"
        revision_eligible_ids = {
            str(item.get("id"))
            for item in output.get("artifacts") or []
            if item.get("format") in OUTPUT_REVISION_FORMATS
        }
        eligible_patches = [
            item for item in report.patches if item.artifact_id in revision_eligible_ids
        ]
        eligible_patch_ids = {item.patch_id for item in eligible_patches}
        wire = {
            "id": report.report_id,
            "status": report.status,
            "providerProfile": report.provider_profile,
            "modelId": report.model_id,
            "targetArtifactSetHash": report.target_artifact_set_hash,
            "guidelineVersion": report.guideline_version,
            "iteration": report.iteration,
            "reviewedArtifactIds": report.reviewed_artifact_ids,
            "reviewRenderHashes": report.review_render_hashes,
            "dataAccessId": report.data_access_id,
            "inspectedRowCount": report.inspected_row_count,
            "findings": [
                {
                    "id": item.finding_id,
                    "ruleId": item.rule_id,
                    "severity": item.severity,
                    "message": item.message,
                    "artifactIds": item.artifact_ids,
                    "blocking": item.blocking,
                    "proposedPatchIds": [
                        patch_id
                        for patch_id in item.proposed_patch_ids
                        if patch_id in eligible_patch_ids
                    ],
                    "evidenceRefs": item.evidence_refs,
                    "requiresUpstreamStage": item.requires_upstream_stage,
                    "upstreamStage": item.upstream_stage,
                }
                for item in report.findings
            ],
            "patches": [
                {
                    "id": item.patch_id,
                    "groupId": item.group_id,
                    "artifactId": item.artifact_id,
                    "rationale": item.rationale,
                    "changes": item.changes,
                }
                for item in eligible_patches
            ],
            "reportDirectives": [
                item.model_dump(mode="json", by_alias=True)
                for item in report.report_directives
                if not item.requires_upstream_stage
            ],
            "semanticReportStatus": report.semantic_report_status,
            "visualRubricVersion": report.visual_rubric_version,
            "visualRubricHash": report.visual_rubric_hash,
            "visualRubricStatus": report.visual_rubric_status,
            "createdAt": report.created_at.isoformat(),
        }
        output["reviewHistory"] = [
            *list(output.get("reviewHistory") or []),
            *([output["reviewReport"]] if output.get("reviewReport") else []),
        ]
        output["reviewReport"] = wire
        output["reviewIteration"] = iteration
        output["reportSemanticStatus"] = report.semantic_report_status
        eligible_directives = [
            item for item in report.report_directives if not item.requires_upstream_stage
        ]
        if eligible_patches or eligible_directives:
            target_ids = {item.artifact_id for item in eligible_patches} | {
                item.artifact_id for item in eligible_directives
            }
            output["pendingProposal"] = {
                "id": f"output-proposal-{report.report_id}",
                "request": "Apply selected Review AI corrections.",
                "summary": "Review AI proposed bounded corrections for selected artifacts.",
                "artifactIds": sorted(target_ids),
                "patches": wire["patches"],
                "reportDirectives": wire["reportDirectives"],
                "targetArtifactSetHash": output.get("artifactSetHash"),
                "targetArtifactHashes": {
                    str(item.get("id")): str(item.get("hash"))
                    for item in output.get("artifacts") or []
                    if item.get("id") in target_ids
                },
            }
        elif output.get("pendingProposal"):
            output.pop("pendingProposal", None)
        append_stage_message(
            session,
            WorkflowStage.OUTPUT,
            "agent",
            (
                f"Reviewed {len(selected)} selected artifact(s): {report.status}. "
                f"Research Report semantic status: {report.semantic_report_status}."
            ),
            target_hash=str(output.get("artifactSetHash") or ""),
            command_type="output_review",
            label="Report Reviewer",
        )
        session["output"] = output
        author = self.manager.report_author
        record_stage_handoff(
            session,
            WorkflowStage.OUTPUT,
            agents=[
                AgentRuntimeDescriptor(
                    role="report_author",
                    authority="author",
                    provider_profile=(author.provider_profile if author else "unavailable"),
                    model_id=(author.model_id if author else "unavailable"),
                    status="available" if author else "unavailable",
                    limitations=[
                        "May rewrite only user-approved report sections and cannot change "
                        "evidence, analysis or approvals."
                    ],
                ),
                AgentRuntimeDescriptor(
                    role="report_reviewer",
                    authority="review",
                    provider_profile=self.output_reviewer.provider_profile,
                    model_id=self.output_reviewer.model_id,
                    status="available",
                    limitations=[
                        "May review and issue directives only; cannot modify artifacts or approve "
                        "Finish."
                    ],
                ),
            ],
        )
        return output

    def _chart_self_checks(self, session_id: str, snapshot_id: str, output: dict[str, Any]) -> bool:
        from macro_research_agent.workflow.publication_rubric import ACADEMIC_VISUAL_RUBRIC

        checker = getattr(self.artifact_author, "check_delivery", None)
        # Network-free author is injected only by offline tests. Production always has this port.
        if checker is None:
            if self.artifact_author.provider_profile != "deterministic-local":
                raise OutputWorkspaceError("The configured chart author has no self-check port.")
            return True
        charts = [
            item
            for item in output.get("artifacts", [])
            if item.get("format") == "svg"
            and item.get("exportSelected")
            and item.get("status") == "ready"
        ]
        if not charts:
            return True
        records = []
        evidence: dict[str, Any] = {}
        try:
            context = self.model_data_access.context_for_snapshot(
                session_id,
                snapshot_id,
                WorkflowStage.OUTPUT,
                for_remote_provider=self.artifact_author.remote_data_disclosure,
                provider_profile=self.artifact_author.provider_profile,
                model_id=self.artifact_author.model_id,
            )
            budget = getattr(self.artifact_author, "max_data_rows", 2000)
            if context.grant.row_count > budget:
                raise OutputWorkspaceError("Chart self-check exceeds the complete-data budget.")
            from macro_research_agent.workflow.stage_assistant import read_all_dataset_rows

            evidence = {
                "datasetHash": context.grant.content_hash,
                "rows": read_all_dataset_rows(context, self.model_data_access),
                "rubric": ACADEMIC_VISUAL_RUBRIC.model_dump(mode="json"),
                "charts": [
                    {
                        "id": item["id"],
                        "hash": item["hash"],
                        "specification": output["artifactSpecifications"][item["id"]],
                        "svg": self.manager.read_artifact_content(
                            session_id, item["id"], item["hash"]
                        ).decode("utf-8"),
                    }
                    for item in charts
                ],
            }
            for number in (1, 2):
                result = checker(evidence, number)
                records.append({"round": number, **result.model_dump(mode="json")})
        except (OutputWorkspaceError, ValueError) as error:
            records.append(
                {
                    "round": len(records) + 1,
                    "status": "error",
                    "issues": [str(error)],
                    "code": getattr(error, "code", "chart_self_check_unavailable"),
                }
            )
        passed = len(records) == 2 and all(item["status"] == "pass" for item in records)
        receipt = {
            "id": f"chart-self-check-{len(output.get('chartSelfChecks', [])) + 1}",
            "provider": self.artifact_author.provider_profile,
            "model": self.artifact_author.model_id,
            "artifactSetHash": output.get("artifactSetHash"),
            "artifactIds": [item["id"] for item in charts],
            "evidenceHash": stable_hash(evidence),
            "rounds": records,
            "status": "pass" if passed else "fail",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        output["chartSelfChecks"] = [*output.get("chartSelfChecks", []), receipt]
        self.repository.record_trace_event(
            session_id,
            "ai.chart_self_checks_completed",
            Actor.AGENT,
            {
                key: receipt[key]
                for key in (
                    "provider",
                    "model",
                    "artifactSetHash",
                    "evidenceHash",
                    "status",
                    "createdAt",
                )
            },
        )
        if not passed:
            if output.get("reviewReport"):
                output["reviewHistory"] = [*output.get("reviewHistory", []), output["reviewReport"]]
            output["reviewReport"] = None
        return passed

    @staticmethod
    def _append_review_node(session: dict[str, Any], output: dict[str, Any]) -> None:
        if not output.get("reviewReport"):
            return
        now = datetime.now(timezone.utc).isoformat()
        report = dict(output.get("reviewReport") or {})
        nodes = list(session.get("nodes") or [])
        kinds = ["output_compliance_review", "visual_artifact_review"]
        if report.get("semanticReportStatus") != "not_applicable":
            kinds.append("semantic_report_review")
        for kind in kinds:
            nodes.append(
                {
                    "id": f"node-{kind}-{len(nodes) + 1}",
                    "kind": kind,
                    "status": "completed",
                    "authority": "review",
                    "inputSnapshotIds": [str(output.get("artifactSetHash"))],
                    "outputSnapshotId": f"{report.get('id')}:{kind}",
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
        session["nodes"] = nodes

    @staticmethod
    def _append_proposal_node(
        session: dict[str, Any], proposal_id: str, output: dict[str, Any]
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        nodes = list(session.get("nodes") or [])
        nodes.append(
            {
                "id": f"node-output-proposal-{proposal_id}",
                "kind": "output_revision",
                "status": "waiting_for_review",
                "authority": "proposal",
                "inputSnapshotIds": [str(output.get("artifactSetHash"))],
                "outputSnapshotId": proposal_id,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        session["nodes"] = nodes

    @staticmethod
    def _close_proposal_node(session: dict[str, Any], proposal_id: str, *, applied: bool) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for node in session.get("nodes") or []:
            if node.get("outputSnapshotId") == proposal_id:
                node["status"] = "completed" if applied else "stale"
                node["updatedAt"] = now
                if not applied:
                    node["staleReason"] = "The user rejected the Output revision proposal."

    @staticmethod
    def _update_manifest_node(
        session: dict[str, Any], manifest_id: str, selected_ids: list[str], updated_at: str
    ) -> None:
        nodes = list(session.get("nodes") or [])
        nodes.append(
            {
                "id": f"node-reproduction_manifest-{len(nodes) + 1}",
                "kind": "reproduction_manifest",
                "status": "completed",
                "inputSnapshotIds": selected_ids,
                "outputSnapshotId": manifest_id,
                "createdAt": updated_at,
                "updatedAt": updated_at,
            }
        )
        session["nodes"] = nodes
