import "@testing-library/jest-dom";

// jsdom lacks ResizeObserver (used by Recharts ResponsiveContainer).
class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = ResizeObserver as any;
}
