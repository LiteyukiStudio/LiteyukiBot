import { createContext, useCallback, useContext, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { useTheme } from "next-themes";

export const accents = ["blue", "lavender", "cyan"] as const;
export type Accent = (typeof accents)[number];
export type ThemeMode = "system" | "light" | "dark";

type Reveal = { x: number; y: number; target: "light" | "dark" };
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

function prefersDark(mode: ThemeMode): boolean {
  return mode === "dark" || (mode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
}

function ThemeReveal({ reveal }: { reveal: Reveal | null }) {
  if (reveal === null) return null;
  return <div className={`webui-theme-reveal webui-theme-reveal--${reveal.target}`} style={{ "--reveal-x": `${reveal.x}px`, "--reveal-y": `${reveal.y}px` } as CSSProperties} />;
}

export function ThemeControllerProvider({ children }: { children: ReactNode }) {
  const { theme, setTheme } = useTheme();
  const [accent, setAccentState] = useState<Accent>(initialAccent);
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const mode = (theme === "light" || theme === "dark" ? theme : "system") as ThemeMode;

  useEffect(() => {
    document.documentElement.dataset.accent = accent;
    try { localStorage.setItem(accentStorageKey, accent); } catch { /* The active session still has its accent. */ }
  }, [accent]);

  const setAccent = useCallback((value: Accent) => setAccentState(value), []);
  const setMode = useCallback((value: ThemeMode, origin?: HTMLElement | null) => {
    if (value === mode) return;
    const target = prefersDark(value) ? "dark" : "light";
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || origin === null || origin === undefined) {
      setTheme(value);
      return;
    }
    const bounds = origin.getBoundingClientRect();
    setReveal({ x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2, target });
    window.setTimeout(() => setTheme(value), 850);
    window.setTimeout(() => setReveal(null), 1_080);
  }, [mode, setTheme]);

  const value = useMemo(() => ({ accent, mode, setAccent, setMode }), [accent, mode, setAccent, setMode]);
  return <ThemeControllerContext.Provider value={value}>{children}<ThemeReveal reveal={reveal} /></ThemeControllerContext.Provider>;
}

export function useThemeController() {
  const value = useContext(ThemeControllerContext);
  if (value === null) throw new Error("useThemeController must be rendered inside ThemeControllerProvider");
  return value;
}
