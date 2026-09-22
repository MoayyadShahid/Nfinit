"use client";

import { Moon, Sun } from "lucide-react";

export type AppTheme = "midnight" | "porcelain";

const THEME_KEY = "nfinit:theme";

function applyTheme(theme: AppTheme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.classList.toggle("dark", theme === "midnight");
  root.style.colorScheme = theme === "midnight" ? "dark" : "light";
  window.localStorage.setItem(THEME_KEY, theme);
  window.dispatchEvent(new CustomEvent("nfinit-theme-change", { detail: theme }));
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  return (
    <button
      type="button"
      onClick={() => {
        const theme =
          document.documentElement.dataset.theme === "porcelain"
            ? "porcelain"
            : "midnight";
        const nextTheme = theme === "midnight" ? "porcelain" : "midnight";
        applyTheme(nextTheme);
      }}
      aria-label="Toggle color theme"
      title="Toggle color theme"
      className={`theme-toggle flex size-9 items-center justify-center rounded-full border transition-all hover:scale-[1.03] ${className}`}
    >
      <Moon className="theme-icon-midnight size-3.5" />
      <Sun className="theme-icon-porcelain size-3.5" />
    </button>
  );
}
