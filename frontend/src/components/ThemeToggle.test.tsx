// Dark mode behavior: the toggle must flip the `dark` class on <html>,
// announce itself accessibly, and persist the explicit choice.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, useTheme } from "../hooks/useTheme";
import { ThemeToggle } from "./ThemeToggle";

function Probe() {
  const { resolvedTheme } = useTheme();
  return <span data-testid="resolved">{resolvedTheme}</span>;
}

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
      <Probe />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.classList.remove("dark");
});

describe("ThemeToggle / ThemeProvider", () => {
  it("defaults to the (light) system preference and exposes the resolved theme", () => {
    renderToggle();
    expect(screen.getByTestId("resolved")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("toggles the dark class on <html> and persists the choice", async () => {
    renderToggle();
    const btn = screen.getByRole("button", { name: /switch to dark theme/i });
    await userEvent.click(btn);
    expect(document.documentElement).toHaveClass("dark");
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
    expect(window.localStorage.getItem("apix-theme")).toBe("dark");

    await userEvent.click(screen.getByRole("button", { name: /switch to light theme/i }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(window.localStorage.getItem("apix-theme")).toBe("light");
  });

  it("keeps an accessible label at all times", async () => {
    renderToggle();
    const btn = screen.getByRole("button", { name: /theme/i });
    expect(btn).toHaveAttribute("aria-label");
    await userEvent.click(btn);
    expect(screen.getByRole("button", { name: /theme/i })).toHaveAttribute("aria-label");
  });
});
