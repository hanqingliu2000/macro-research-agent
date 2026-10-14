# Project documentation

Start with the [project README](../README.md) for the product, local setup and limitations.
[Current implementation status](development/current_status.md) distinguishes working code,
historical acceptance and unfinished work. This is experimental, local single-user software.

## Product and implementation contracts

| Topic | Documents |
| --- | --- |
| Architecture and isolation | [Architecture](development/architecture.md), [repository structure](development/repository_structure.md) |
| Workflow state and authorization | [State graph](development/state_graph.md), [status and routes](development/workflow_status_and_routes.md), [stage protocols](development/workflow_stage_protocols.md) |
| AI roles and access | [Capability orchestration](development/ai_capability_orchestration.md), [provider profiles](development/provider_profiles.md), [security policy](../SECURITY.md) |
| Agent autonomy and budgets | [Agent contract](development/agent_mode.md), [Agent milestones](development/agent_implementation_plan.md) |
| API and diagnostics | [API contract](development/api_contract.md), [trace and reproduction](development/trace_and_reproducibility.md) |
| Data discovery and acquisition | [Source catalog](data_sources/source_catalog.md), [connector contract](development/connector_contract.md), [robustness standard](development/connector_robustness_standard.md), [IMF dataflow admission](development/imf_dataflow_onboarding.md) |
| Output quality | [Active academic placeholder](../guidelines/academic-publication-placeholder-v1.md), [rubric status](../guidelines/visual-review-rubric-status.md), [workbook templates](../guidelines/templates/README.md) |
| UI conventions | [Design system](development/ui_design_system.md) |

## Plans and evidence

- [Development plan](development/implementation_plan.md): ordered phase scope and exit criteria.
- [Longitudinal acceptance scenario](development/longitudinal_acceptance_scenario.md): the complete
  multi-day Workflow specification; a test case is not an executed pass.
- [Browser-run evidence](testing/browser-runs/README.md): retained actual outcomes, including
  failures, partial coverage and the open Agent A6 gate.
- [Phase 0–3 baseline](development/phase0_to_phase3_acceptance_report.md),
  [Phase 2](development/phase2_acceptance_report.md),
  [Phase 3](development/phase3_acceptance_report.md),
  [Plan AI](development/plan_ai_acceptance_report.md) and
  [catalog acceptance](development/source_index_catalog_acceptance_report.md): historical scoped
  evaluations, not blanket acceptance of every subsequent change.
- [Public release review](development/public_release_review.md): current alignment and source-only
  release checks.
- [Contribution checks](../CONTRIBUTING.md): reproducible offline lint, type, unit and build commands.

## Reading historical decisions

[ADRs](adr/) preserve why boundaries were chosen. Later amendments supersede older decisions;
historical wording must not be used to reactivate a disabled provider or bypass current gates.
Earlier phase descriptions and old test counts retain their dates and limited scopes.

Historical issue and revision labels in test records refer to development evidence and need not
exist as Git objects or issue numbers in this public source distribution. No runtime database,
private diagnostics, model-response dump or prior repository discussion is included.

Provider metadata and dependencies keep their own terms; see
[third-party notices](../THIRD_PARTY_NOTICES.md). The project has no open-source license grant.
