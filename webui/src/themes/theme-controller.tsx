import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTheme } from "next-themes";

export const accents = ["blue", "lavender", "cyan"] as const;
export type Accent = (typeof accents)[number];
export type ThemeMode = "system" | "light" | "dark";

type ThemeControllerValue = {
  accent: Accent;
  mode: ThemeMode;
  setAccent: (accent: Accent) => void;
  setMode: (mode: ThemeMode, origin?: HTMLElement | null) => void;
};

const accentStorageKey = "liteyukibot.webui.accent";
const ThemeControllerContext = createContext<ThemeControllerValue | null>(null);

function initialAccent(): Accent {
  try {
    const value = localStorage.getItem(accentStorageKey);
    return accents.includes(value as Accent) ? value as Accent : "blue";
  } catch {
    return "blue";
  }
}

/**
 * Provides persistent theme mode and accent state to the WebUI tree.
 * @param props - Child React nodes rendered inside the theme controller.
 * @returns The theme context provider.
 * @remarks Storage failures are intentionally non-fatal; the current page retains its in-memory choice.
 */
export function ThemeControllerProvider({ children }: { children: ReactNode }) {
  const { theme, setTheme } = useTheme();
  const [accent, setAccentState] = useState<Accent>(initialAccent);
  const transitionTimer = useRef<number | null>(null);
  const mode = (theme === "light" || theme === "dark" ? theme : "system") as ThemeMode;

  useEffect(() => {
    document.documentElement.dataset.accent = accent;
    try { localStorage.setItem(accentStorageKey, accent); } catch { /* The active session still has its accent. */ }
  }, [accent]);

  useEffect(() => () => {
    if (transitionTimer.current !== null) window.clearTimeout(transitionTimer.current);
    document.documentElement.classList.remove("webui-theme-transition");
  }, []);

  const setAccent = useCallback((value: Accent) => setAccentState(value), []);
  const setMode = useCallback((value: ThemeMode, _origin?: HTMLElement | null) => {
    if (value === mode) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setTheme(value);
      return;
    }
    if (transitionTimer.current !== null) window.clearTimeout(transitionTimer.current);
    document.documentElement.classList.add("webui-theme-transition");
    window.requestAnimationFrame(() => setTheme(value));
    transitionTimer.current = window.setTimeout(() => {
      document.documentElement.classList.remove("webui-theme-transition");
      transitionTimer.current = null;
    }, 950);
  }, [mode, setTheme]);

  const value = useMemo(() => ({ accent, mode, setAccent, setMode }), [accent, mode, setAccent, setMode]);
  return <ThemeControllerContext.Provider value={value}>{children}</ThemeControllerContext.Provider>;
}

/**
 * Reads theme state and mutation methods from the nearest provider.
 * @returns The current accent, mode, and setters.
 * @throws When called outside `ThemeControllerProvider`.
 */
export function useThemeController() {
  const value = useContext(ThemeControllerContext);
  if (value === null) throw new Error("useThemeController must be rendered inside ThemeControllerProvider");
  return value;
}
