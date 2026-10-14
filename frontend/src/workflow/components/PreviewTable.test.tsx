import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DatasetColumn } from "../domain/types";
import { DATA_PREVIEW_PAGE_SIZE, PreviewTable } from "./PreviewTable";

const columns: DatasetColumn[] = [
  { id: "provider", label: "Provider", dataType: "string", role: "attribute", required: false, key: false },
  { id: "dataset", label: "Dataset", dataType: "string", role: "attribute", required: false, key: false },
  { id: "series_id", label: "Series ID", dataType: "string", role: "series_id", required: true, key: true },
  { id: "entity_code", label: "Entity code", dataType: "string", role: "entity_code", required: true, key: true },
  { id: "indicator_code", label: "Indicator", dataType: "string", role: "indicator_code", required: true, key: true },
  { id: "frequency", label: "Frequency", dataType: "string", role: "frequency", required: true, key: true },
  { id: "period", label: "Period", dataType: "period", role: "period", required: true, key: true },
  { id: "value", label: "Value", dataType: "number", role: "value", required: true, key: false },
  { id: "unit", label: "Unit", dataType: "string", role: "attribute", required: false, key: false },
];

describe("PreviewTable", () => {
  it("prioritizes research observation fields in the first six columns", () => {
    render(
      <PreviewTable
        caption="IMF WEO"
        columns={columns}
        rows={[{
          entity_code: "CHN",
          indicator_code: "GGXWDG_NGDP",
          period: "2024",
          value: 90.421,
          unit: "Percent of GDP",
          frequency: "annual",
        }]}
      />,
    );

    const headers = within(screen.getByRole("table")).getAllByRole("columnheader");
    expect(headers.map((header) => header.textContent?.replace(/string|number|period/g, ""))).toEqual([
      "#",
      "Entity code",
      "Indicator",
      "Period",
      "Value",
      "Unit",
      "Frequency",
    ]);
    expect(screen.getByRole("cell", { name: "2024" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "90.421" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Percent of GDP" })).toBeInTheDocument();
    expect(screen.queryByText(/Mock preview/)).not.toBeInTheDocument();
  });

  it.each([9, 56, 100, 101])(
    "renders the actual first and last row on every page of a %i-row dataset",
    (total) => {
      const rows = Array.from({ length: total }, (_, index) => ({
        entity_code: `ROW-${index + 1}`,
        indicator_code: "TEST",
        period: String(2000 + index),
        value: index + 1,
        unit: "Index",
        frequency: "annual",
      }));
      const firstPage = rows.slice(0, DATA_PREVIEW_PAGE_SIZE);
      const view = render(
        <PreviewTable caption="Pagination test" columns={columns} rows={firstPage} />,
      );

      for (let offset = 0; offset < total; offset += DATA_PREVIEW_PAGE_SIZE) {
        const page = rows.slice(offset, offset + DATA_PREVIEW_PAGE_SIZE);
        view.rerender(
          <PreviewTable
            caption="Pagination test"
            columns={columns}
            rowOffset={offset}
            rows={page}
          />,
        );
        expect(screen.getByRole("cell", { name: `ROW-${offset + 1}` })).toBeInTheDocument();
        expect(
          screen.getByRole("cell", { name: `ROW-${offset + page.length}` }),
        ).toBeInTheDocument();
        expect(
          screen.getByText(`Rows ${offset + 1}–${offset + page.length}`),
        ).toBeInTheDocument();
      }
    },
  );
});
