import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DeltaBadge } from "./badges";

describe("DeltaBadge", () => {
  it("shows an increase with up arrow", () => {
    render(<DeltaBadge value={2.4} />);
    expect(screen.getByText("+2.4%")).toBeInTheDocument();
  });

  it("shows a decrease", () => {
    render(<DeltaBadge value={-3.1} />);
    expect(screen.getByText("-3.1%")).toBeInTheDocument();
  });

  it("shows a neutral state for null", () => {
    render(<DeltaBadge value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
