# Publication templates

The registered `research-workbook-v1` contract is the active structural workbook template and is
mirrored in `research-workbook-v1.yaml`. The typed `publication-v1` rule set remains the governing
chart/table standard; later product-owner workbook files may add stricter layout rules.

Phase 1E renderers and Review AI must resolve a versioned template/guideline ID from the registry.
The visual reviewer receives a direct generated render plus the applicable rule subset and returns
a typed `OutputReviewReport`; it cannot modify template files or waive deterministic checks.

The current linter verifies required sheets and columns, sheet order, frozen headers, filters on
populated tables, formula-free analytical/chart data, absence of external links, guideline metadata,
conditional forecast/IRF sheets and an embedded chart when selected.

Future template additions must include:

- source and version;
- supported chart/table types;
- required cells, named ranges and sheets;
- editable versus protected regions;
- a deterministic fixture workbook for structural tests;
- a human-approved reference description without requiring screenshot-based CI.
