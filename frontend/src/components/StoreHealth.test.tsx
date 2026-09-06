import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { StoreCounts } from "../lib/types";
import { StoreHealthBanner } from "./StoreHealth";

const ephemeralStore: StoreCounts = {
  observations: 0,
  valid_observations: 0,
  raw_payloads: 0,
  runs: 0,
  days_collected: 0,
  by_status: {},
  db_bytes: 0,
  available: true,
  backend: "sqlite",
  ephemeral: true,
  durable: false,
  ignores_database_url: true,
};

describe("StoreHealthBanner", () => {
  it("shows the ignored DATABASE_URL and temporary-storage caveat from the API", () => {
    const note =
      "DATABASE_URL is ignored (APIX_IGNORE_DATABASE_URL=1; default on Vercel). " +
      "Data is lost on a cold start or redeploy. " +
      "For durable history, set APIX_IGNORE_DATABASE_URL=0 and DATABASE_URL to PostgreSQL.";
    render(<StoreHealthBanner store={{ ...ephemeralStore, note }} />);

    expect(screen.getByText("Ephemeral collection store (serverless /tmp)")).toBeInTheDocument();
    expect(screen.getByText(note)).toBeInTheDocument();
  });

  it("includes the PostgreSQL opt-in in the fallback instructions", () => {
    render(<StoreHealthBanner store={ephemeralStore} />);

    expect(screen.getByText(/APIX_IGNORE_DATABASE_URL=0 and DATABASE_URL/)).toBeInTheDocument();
    expect(screen.getByText(/lost on a cold start or redeploy/)).toBeInTheDocument();
  });

  it("does not warn when the explicitly enabled PostgreSQL store is healthy", () => {
    const { container } = render(
      <StoreHealthBanner
        store={{
          ...ephemeralStore,
          backend: "postgresql",
          ephemeral: false,
          durable: true,
          ignores_database_url: false,
        }}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
