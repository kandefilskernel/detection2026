import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "Segoe UI", "system-ui", "-apple-system", "Roboto", "Arial", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        elevated: "hsl(var(--elevated))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        accent: "hsl(var(--accent))",
        sidebar: { DEFAULT: "hsl(var(--sidebar))", foreground: "hsl(var(--sidebar-foreground))", border: "hsl(var(--sidebar-border))" },
        risk: {
          critique: "hsl(var(--risk-critique))",
          eleve: "hsl(var(--risk-eleve))",
          moyen: "hsl(var(--risk-moyen))",
          faible: "hsl(var(--risk-faible))",
        },
        warn: "hsl(var(--warn-text))",
      },
      borderRadius: { xl: "1rem", lg: "0.75rem", md: "0.5rem", sm: "0.375rem" },
      boxShadow: {
        card: "0 1px 2px hsl(var(--shadow) / 0.06), 0 0 0 1px hsl(var(--shadow) / 0.03)",
        float: "0 12px 32px -12px hsl(var(--shadow) / 0.35), 0 2px 6px hsl(var(--shadow) / 0.08)",
        glow: "0 0 0 1px hsl(var(--primary) / 0.25), 0 8px 24px -8px hsl(var(--primary) / 0.55)",
      },
      keyframes: {
        "fade-up": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        shimmer: { from: { backgroundPosition: "-200% 0" }, to: { backgroundPosition: "200% 0" } },
      },
      animation: {
        "fade-up": "fade-up .35s cubic-bezier(.2,.7,.2,1) both",
        shimmer: "shimmer 1.6s linear infinite",
      },
    },
  },
  plugins: [],
};
export default config;
