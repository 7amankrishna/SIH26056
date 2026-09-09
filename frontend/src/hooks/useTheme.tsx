// Theme (light/dark/system) for the whole dashboard.
//
// - Persisted in localStorage ("apix-theme"), defaults to the OS preference.
// - Applied by toggling the `dark` class on <html>; the pre-paint inline
//   script in index.html does the same before React mounts (no white flash).
// - `resolvedTheme` lets charts and other non-CSS consumers pick colors.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemeChoice = "light" | "dark" | "system";

const STORAGE_KEY = "apix-theme";

function systemDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function readStored(): ThemeChoice {
  if (typeof window === "undefined") return "system";
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "light" || v === "dark" || v === "system" ? v : "system";
}

function apply(choice: ThemeChoice): "light" | "dark" {
  const resolved = choice === "system" ? (systemDark() ? "dark" : "light") : choice;
  document.documentElement.classList.toggle("dark", resolved === "dark");
  return resolved;
}

interface ThemeValue {
  /** what the user picked (or the default: system) */
  theme: ThemeChoice;
  /** what is actually on screen right now */
  resolvedTheme: "light" | "dark";
  setTheme: (t: ThemeChoice) => void;
  toggle: () => void;
}

const ThemeCtx = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setChoice] = useState<ThemeChoice>(readStored);
  const [resolvedTheme, setResolved] = useState<"light" | "dark">(() => apply(readStored()));

  // Re-resolve when the OS preference flips while in "system".
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (readStored() === "system") setResolved(apply("system"));
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const setTheme = useCallback((t: ThemeChoice) => {
    setChoice(t);
    try {
      window.localStorage.setItem(STORAGE_KEY, t);
    } catch {
      /* private mode — choice just won't persist */
    }
    setResolved(apply(t));
  }, []);

  const value = useMemo<ThemeValue>(
    () => ({
      theme,
      resolvedTheme,
      setTheme,
      toggle: () => setTheme(resolvedTheme === "dark" ? "light" : "dark"),
    }),
    [theme, resolvedTheme, setTheme],
  );

  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export function useTheme(): ThemeValue {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}

declare global {
  interface Window {
    matchMedia: (query: string) => MediaQueryList;
  }
}
