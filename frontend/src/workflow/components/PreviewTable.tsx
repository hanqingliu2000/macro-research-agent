import type { DatasetColumn, DatasetRow } from "../domain/types";

export const DATA_PREVIEW_PAGE_SIZE = 8;

const previewColumnPriority = [
  "entity_code",
  "indicator_code",
  "period",
  "value",
  "unit",
  "frequency",
];

function previewColumns(columns: DatasetColumn[]) {
  const byId = new Map(columns.map((column) => [column.id, column]));
  const prioritized = previewColumnPriority
    .map((id) => byId.get(id))
    .filter((column): column is DatasetColumn => column !== undefined);
  const remaining = columns.filter((column) => !previewColumnPriority.includes(column.id));
  return [...prioritized, ...remaining].slice(0, 6);
}

export function PreviewTable({
  columns,
  rows,
  caption,
  rowOffset = 0,
  loading = false,
}: {
  columns: DatasetColumn[];
  rows: DatasetRow[];
  caption: string;
  rowOffset?: number;
  loading?: boolean;
}) {
  const visible = previewColumns(columns);
  const rowKey = (row: DatasetRow) =>
    [row.series_id, row.entity_code, row.indicator_code, row.frequency, row.period]
      .map(String)
      .join(":");
  return (
    <div className="dataset-preview">
      <div className="preview-title-row">
        <div>
          <p className="panel-kicker">DATA PREVIEW</p>
        </div>
        <span>
          {loading
            ? "Loading rows…"
            : rows.length
              ? `Rows ${rowOffset + 1}–${rowOffset + rows.length}`
              : "No rows"}
        </span>
      </div>
      <div className="preview-table-scroll">
        <table>
          <caption className="sr-only">
            {caption}, rows {rowOffset + 1}–{rowOffset + rows.length}
          </caption>
          <thead><tr><th aria-label="Row number" className="row-number">#</th>{visible.map((column) => <th key={column.id} scope="col">{column.label}<span className="column-type">{column.dataType}</span></th>)}</tr></thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowKey(row)}>
                <th className="row-number" scope="row">{rowOffset + rowIndex + 1}</th>
                {visible.map((column) => <td className={row[column.id] == null ? "null-value" : undefined} key={column.id}>{row[column.id] ?? "null"}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
