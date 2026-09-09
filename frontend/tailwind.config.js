/**
 * APIx design tokens — single source of truth.
 *
 * Every color is a CSS-variable triplet (`--token: R G B`) defined in
 * src/index.css for `:root` (light) and `.dark`, surfaced here as
 * `rgb(var(--token) / <alpha-value>)`. Flipping the `dark` class on <html>
 * re-themes the entire app — no component knows a hex value.
 */

const v = (name: string) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // surfaces
        page: v("--page"),
        surface: v("--surface"),
        elevated: v("--elevated"),
        code: {
          bg: v("--code-bg"),
          fg: v("--code-fg"),
          muted: v("--code-muted"),
        },
        // neutral text + fill scale (inverts in dark mode)
        ink: {
          900: v("--ink-900"),
          800: v("--ink-800"),
          700: v("--ink-700"),
          600: v("--ink-600"),
          500: v("--ink-500"),
          400: v("--ink-400"),
          300: v("--ink-300"),
          200: v("--ink-200"),
          100: v("--ink-100"),
          50: v("--ink-50"),
        },
        // brand (cyan) — re-tuned for AA on solid buttons in both themes
        brand: {
          700: v("--brand-700"),
          600: v("--brand-600"),
          500: v("--brand-500"),
          400: v("--brand-400"),
          300: v("--brand-300"),
          50: v("--brand-50"),
        },
        accent: v("--accent"),
        accentFg: v("--accent-fg"),

        // semantic scales (chips, badges, deltas) — dark values chosen for AA
        // on dark surfaces; light values are the Tailwind defaults.
        emerald: {
          50: v("--emerald-50"),
          100: v("--emerald-100"),
          200: v("--emerald-200"),
          300: v("--emerald-300"),
          400: v("--emerald-400"),
          500: v("--emerald-500"),
          600: v("--emerald-600"),
          700: v("--emerald-700"),
          800: v("--emerald-800"),
          900: v("--emerald-900"),
        },
        amber: {
          50: v("--amber-50"),
          100: v("--amber-100"),
          200: v("--amber-200"),
          500: v("--amber-500"),
          600: v("--amber-600"),
          700: v("--amber-700"),
          800: v("--amber-800"),
        },
        red: {
          50: v("--red-50"),
          100: v("--red-100"),
          200: v("--red-200"),
          400: v("--red-400"),
          500: v("--red-500"),
          600: v("--red-600"),
          700: v("--red-700"),
          800: v("--red-800"),
        },
        sky: {
          50: v("--sky-50"),
          100: v("--sky-100"),
          200: v("--sky-200"),
          400: v("--sky-400"),
          500: v("--sky-500"),
          600: v("--sky-600"),
          700: v("--sky-700"),
          800: v("--sky-800"),
        },
        purple: {
          50: v("--purple-50"),
          700: v("--purple-700"),
        },
        violet: {
          50: v("--violet-50"),
          700: v("--violet-700"),
        },
        orange: {
          50: v("--orange-50"),
          700: v("--orange-700"),
        },
        slate: {
          200: v("--slate-200"),
          400: v("--slate-400"),
        },
        cyan: {
          50: v("--cyan-50"),
          200: v("--cyan-200"),
          700: v("--cyan-700"),
        },
      },
      fontFamily: {
        sans: [
          "Inter Variable",
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        // 3 elevation levels; the CSS vars weaken shadows in dark mode where
        // surfaces + borders carry the depth instead.
        card: "var(--shadow-card)",
        pop: "var(--shadow-pop)",
        overlay: "var(--shadow-overlay)",
      },
      transitionDuration: {
        DEFAULT: "150ms",
      },
    },
  },
  plugins: [],
} as const;
