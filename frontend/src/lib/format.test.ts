import { describe, expect, it } from "vitest";
import {
  formatINR,
  formatNumber,
  formatPercent,
  formatIndex,
  formatDate,
  shortDate,
} from "./format";

describe("format helpers", () => {
  it("formats INR with Indian grouping", () => {
    expect(formatINR(6840)).toBe("₹6,840");
    expect(formatINR(123456)).toBe("₹1,23,456");
  });

  it("handles null/undefined", () => {
    expect(formatINR(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatIndex(null)).toBe("—");
  });

  it("formats percent with sign", () => {
    expect(formatPercent(3.8)).toBe("+3.8%");
    expect(formatPercent(-6.1)).toBe("-6.1%");
    expect(formatPercent(0)).toBe("0.0%");
  });

  it("formats index", () => {
    expect(formatIndex(127.4)).toBe("127.4");
  });

  it("formats numbers", () => {
    expect(formatNumber(48291)).toBe("48,291");
  });

  it("formats dates", () => {
    expect(formatDate("2026-08-12")).toMatch(/12/);
    expect(shortDate("2026-08-12")).toMatch(/Aug/);
  });
});
