import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { getStoredTheme, setTheme } from "../lib/theme";

function effectiveIsDark(): boolean {
  const stored = getStoredTheme();
  if (stored === "dark") return true;
  if (stored === "light") return false;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(effectiveIsDark);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = () => setIsDark(effectiveIsDark());
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, []);

  function toggle() {
    const next = !isDark;
    setTheme(next ? "dark" : "light");
    setIsDark(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="flex h-8 w-8 items-center justify-center rounded-md text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
