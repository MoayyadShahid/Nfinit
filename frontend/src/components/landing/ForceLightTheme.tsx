"use client";

import { useEffect } from "react";

const THEME_KEY = "nfinit:theme";

function applyTheme(theme: "porcelain" | "midnight") {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.classList.toggle("dark", theme === "midnight");
  root.style.colorScheme = theme === "midnight" ? "dark" : "light";
}

/**
 * Marketing pages are always light and have no theme toggle. On client-side
 * navigation into the studio this restores the visitor's saved theme.
 */
export function ForceLightTheme() {
  useEffect(() => {
    applyTheme("porcelain");
    return () => {
      let saved: string | null = null;
      try {
        saved = window.localStorage.getItem(THEME_KEY);
      } catch {
        // Storage can be unavailable; fall back to the default.
      }
      applyTheme(saved === "midnight" ? "midnight" : "porcelain");
    };
  }, []);

  return null;
}
