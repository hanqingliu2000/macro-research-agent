# ADR 0007: Four-stage Workflow workspace

Status: accepted

Date: 2026-08-24

## Decision

Workflow Mode uses four independently routed stages:

1. Plan, including clarification;
2. Data;
3. Transformation, including typed model jobs;
4. Output.

The frontend routes are `/sessions/{id}/plan`, `/data`, `/transformation` and `/output`.
The former five-step progress control, global discussion panel, Model tab and Steps tab are
removed. Plan and Output own separate, stage-scoped chat threads. Data and Transformation are
direct-manipulation workspaces without chat.

The Plan screen shows one current plan. Internally, every accepted edit creates an immutable
snapshot, typed state-graph relationships and an append-only event so stale downstream work can be
identified and reproduced. These snapshots are not presented as user-facing plan versions.

## Checkpoints

- Plan Next confirms scope and authorizes acquisition.
- Transformation Run confirms the active dataset, transformation pipeline and model jobs before
  execution.
- Output Finish freezes the selected artifact set and reproduction manifest.

Data Next selects the active dataset for pipeline configuration but is not permission to execute
the pipeline.

## Upstream revisions

Viewing an earlier stage has no effect. Saving an upstream change first displays its impact. On
confirmation, prior downstream snapshots remain readable as stale, current downstream pointers
are cleared and no work reruns automatically.

## External cleaning

The supported round trip is a controlled XLSX workbook with editable data plus schema,
provenance, instructions and a locked manifest. Reimport uses an explicit mapping and validation
wizard. Copy/paste is not a full-dataset interchange mechanism.

## Consequences

- The route is a projection over the durable state graph, never the source of truth (ADR 0013).
- LLM responses are typed proposals and cannot advance stages or run capabilities.
- Data preparation and analytical transformations have separate operation histories.
- Agent Mode routes, providers, storage and sessions remain unchanged.
