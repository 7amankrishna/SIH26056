// Render smoke test for the dashboard shell and Overview page with mocked APIs.
// Catches component-level runtime errors that TypeScript cannot.

import { describe, it, expect, beforeAll, afterAll, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../App";
import { ThemeProvider } from "../hooks/useTheme";

function queryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
}

const overview = {
  current_apix: 114.97,
  daily_change: -1.14,
  weekly_change: 1.37,
  monthly_change: 4.57,
  observation_count: 71925,
  valid_observation_count: 67241,
  route_count: 24,
  airline_count: 6,
  source_count: 5,
  quality_score: 96.8,
  last_collection: "2026-09-06",
  last_run_at: "2026-09-06T09:10:00+05:30",
  index_freshness: "fresh",
  demo_mode: true,
  data_period: { start: "2026-06-09", end: "2026-09-06" },
  base_period: { start: "2026-06-09", end: "2026-06-15" },
  methodology_version: "apix-1.0.0",
  weight_version: "provisional-dgca-v0",
};

const route = {
  route: "DEL-BOM",
  origin: "DEL",
  destination: "BOM",
  origin_city: "Delhi",
  destination_city: "Mumbai",
  current_fare: 6840,
  route_index: 115.6,
  change_24h: 0.4,
  change_7d: 2.1,
  base_price: 5920,
  weight: 0.072,
  observations: 1428,
  quality: 96,
  airlines: 4,
  sparkline: [6000, 6100, 6050, 6300, 6400, 6840],
};

const trend = {
  range: "90d",
  base_period: { start: "2026-06-09", end: "2026-06-15" },
  current: 114.97,
  change_7d: 1.37,
  change_30d: 4.57,
  methodology_version: "apix-1.0.0",
  series: [
    { date: "2026-09-05", apix: 114.3, observations: 800, routes: 24, change: 0.2 },
    { date: "2026-09-06", apix: 114.97, observations: 797, routes: 24, change: 0.6 },
  ],
};

function mockFetch(url: string) {
  if (url.includes("/api/overview")) return Promise.resolve({ ok: true, json: () => Promise.resolve(overview) });
  if (url.includes("/api/index/trend")) return Promise.resolve({ ok: true, json: () => Promise.resolve(trend) });
  if (url.includes("/api/routes/heatmap") || url.includes("/api/routes")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ routes: [route] }) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
}

describe("App render smoke test", () => {
  beforeAll(() => {
    vi.stubGlobal("fetch", vi.fn(mockFetch));
  });
  afterAll(() => {
    vi.unstubAllGlobals();
  });

  it("renders the Overview dashboard without throwing", async () => {
    render(
      <QueryClientProvider client={queryClient()}>
        <ThemeProvider>
          <MemoryRouter initialEntries={["/"]}>
            <App />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Airfare Price Index" })).toBeInTheDocument();
    expect(screen.getByText("DEMO DATA")).toBeInTheDocument();
  });

  // Every route must mount cleanly with sparse API responses — catches runtime
  // regressions (undefined fields, broken hooks) that TypeScript cannot.
  it.each([
    ["/", "Overview"],
    ["/index", "Airfare Index · APIx"],
    ["/routes", "Routes"],
    ["/airlines", "Airline Price Intelligence"],
    ["/lead-time", "Lead-Time Elasticity"],
    ["/collection", "Collection Monitor"],
    ["/api", "API / Data Access"],
  ])("renders %s without throwing", async (path, heading) => {
    const { unmount } = render(
      <QueryClientProvider client={queryClient()}>
        <ThemeProvider>
          <MemoryRouter initialEntries={[path]}>
            <App />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: heading }, { timeout: 2000 })).toBeInTheDocument();
    unmount();
  });

  it("keeps the document title in sync with the route", async () => {
    render(
      <QueryClientProvider client={queryClient()}>
        <ThemeProvider>
          <MemoryRouter initialEntries={["/routes"]}>
            <App />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );
    await screen.findByRole("heading", { name: "Routes" });
    expect(document.title).toBe("Routes · APIx");
  });
});
