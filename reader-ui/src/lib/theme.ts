// Light/dark: follows prefers-color-scheme by default, with a manual
// override stored in localStorage (design brief: "Support light and dark
// following prefers-color-scheme, with a manual toggle stored in
// localStorage"). The override is applied as documentElement's data-theme
// attribute; index.css reads that attribute (or the media query, when
// unset) to pick the token values.

export type ThemePreference = "light" | "dark" | "system";

const STORAGE_KEY = "kos-reader-theme";

export function getStoredTheme(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "light" || value === "dark") return value;
  } catch {
    // Storage can throw in a private window or with site data blocked;
    // fall back to following the system theme.
  }
  return "system";
}

export function applyStoredTheme(): void {
  const preference = getStoredTheme();
  if (preference === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", preference);
  }
}

export function setTheme(preference: ThemePreference): void {
  try {
    if (preference === "system") {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, preference);
    }
  } catch {
    // Best effort only; the in-memory attribute still updates below.
  }
  applyStoredTheme();
}
