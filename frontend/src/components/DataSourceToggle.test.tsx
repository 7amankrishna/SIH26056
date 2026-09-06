// The toggle is the entry point to the whole live-data story: it must call the
// backend (not just flip local state), reflect what the backend says it is
// actually serving, and refuse to look switchable when the server pins it.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { DataSourceToggle } from "./DataSourceToggle";
import { DataSourceProvider } from "../hooks/useDataSource";
import * as apiMod from "../lib/api";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      dataSource: vi.fn(),
      setDataSource: vi.fn(),
      collectStatus: vi.fn(),
      collectPolicy: vi.fn(),
      runSweepBackground: vi.fn(),
    },
  };
});

const demoState = {
  mode: "demo",
  effective_mode: "demo",
  has_live_data: false,
  collector_enabled: true,
  background_running: true,
  store: { observations: 0, valid_observations: 0, raw_payloads: 0, runs: 0, days_collected: 0, by_status: {}, db_bytes: 0 },
  sources: [],
  note: null,
};

function renderToggle() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DataSourceProvider>
          <DataSourceToggle withCollectButton={false} />
        </DataSourceProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(apiMod.api.dataSource).mockResolvedValue(demoState as never);
  vi.mocked(apiMod.api.collectStatus).mockResolvedValue({ ...demoState, queries_per_sweep: 0, lead_times: [], current_run: null, politeness: {} } as never);
  vi.mocked(apiMod.api.setDataSource).mockResolvedValue({ ...demoState, mode: "live" } as never);
  vi.mocked(apiMod.api.runSweepBackground).mockResolvedValue({ accepted: true, detail: "sweep scheduled" } as never);
});

afterEach(() => vi.clearAllMocks());

describe("DataSourceToggle", () => {
  it("renders both data sources and shows demo as selected", () => {
    renderToggle();
    const sw = screen.getByRole("switch");
    expect(screen.getByText("Demo data")).toBeInTheDocument();
    expect(screen.getByText("Scraper")).toBeInTheDocument();
    expect(sw).toHaveAttribute("aria-checked", "false");
  });

  it("posts the mode change to the backend instead of only flipping UI state", async () => {
    renderToggle();
    await userEvent.click(screen.getByRole("switch"));
    await waitFor(() => expect(apiMod.api.setDataSource).toHaveBeenCalledWith("live"));
  });

  it("runs a sweep when switching to live with an empty store", async () => {
    renderToggle();
    await userEvent.click(screen.getByRole("switch"));
    await waitFor(() => expect(apiMod.api.runSweepBackground).toHaveBeenCalled());
  });

  it("refuses to act interactive when APIX_DATA_MODE pins the source", async () => {
    vi.mocked(apiMod.api.dataSource).mockResolvedValue({ ...demoState, locked: true, mode: "demo" } as never);
    vi.mocked(apiMod.api.setDataSource).mockRejectedValue(new Error("locked") as never);
    renderToggle();
    expect(await screen.findByText("demo (locked)")).toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(apiMod.api.setDataSource).not.toHaveBeenCalled();
  });
});
