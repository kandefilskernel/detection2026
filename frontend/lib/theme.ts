"use client";
import { useEffect, useState } from "react";

const KEY = "fraud-rdc-theme";
export type Theme = "light" | "dark";

/** Thème clair / sombre, mémorisé par navigateur (appliqué avant rendu par app/layout.tsx). */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    setTheme(document.documentElement.classList.contains("dark") ? "dark" : "light");
    const obs = new MutationObserver(() =>
      setTheme(document.documentElement.classList.contains("dark") ? "dark" : "light"));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try { localStorage.setItem(KEY, next); } catch { /* navigation privée */ }
  };
  return { theme, toggle };
}
