import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { WebUiPresentation } from "@/models/api";

const storageKey = "liteyukibot.webui.locale";
const supportedLocales = ["en-US", "zh-CN"] as const;
// The presentation endpoint is unavailable on this recovery path, so the
// browser needs a tiny English fallback rather than showing machine keys.
const recoveryMessages: Record<string, string> = {
  "webui.error.unavailable": "Local service unavailable",
  "webui.error.unavailable_detail": "The WebUI could not read the running daemon.",
  "webui.action.retry": "Retry",
};

export type Locale = (typeof supportedLocales)[number];

export type Presentation = {
  locale: Locale;
  locales: Locale[];
  messages: Record<string, string>;
  webuiVersion: string;
};

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  presentation: Presentation | null;
  applyPresentation: (presentation: WebUiPresentation) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);
type LocaleActionsContextValue = Pick<LocaleContextValue, "setLocale" | "applyPresentation"> & { getLocale: () => Locale };
const LocaleActionsContext = createContext<LocaleActionsContextValue | null>(null);

function initialLocale(): Locale {
  try {
    return normalizeLocale(localStorage.getItem(storageKey) ?? navigator.language);
  } catch {
    return "en-US";
  }
}

function normalizeLocale(value: string | null | undefined): Locale {
  return value?.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  const [presentation, setPresentation] = useState<Presentation | null>(null);
  const localeRef = useRef(locale);
  const setLocale = useCallback((next: Locale) => { localeRef.current = next; setLocaleState(next); }, []);
  const getLocale = useCallback(() => localeRef.current, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    try {
      localStorage.setItem(storageKey, locale);
    } catch {
      // Locale selection remains active for the current page.
    }
  }, [locale]);

  const applyPresentation = useCallback((value: WebUiPresentation) => {
    const resolvedLocale = normalizeLocale(value.locale);
    const locales = value.locales.filter((item): item is Locale => supportedLocales.includes(item as Locale));
    setPresentation({ locale: resolvedLocale, locales, messages: value.messages, webuiVersion: value.webui_version });
  }, []);
  const t = useCallback((key: string, values: Record<string, string | number> = {}) => {
    const template = presentation?.messages[key] ?? recoveryMessages[key] ?? key;
    return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (placeholder, name: string) => String(values[name] ?? placeholder));
  }, [presentation]);
  const value = useMemo(
    () => ({ locale, setLocale, presentation, applyPresentation, t }),
    [locale, presentation, applyPresentation, t],
  );
  const actions = useMemo(() => ({ setLocale, applyPresentation, getLocale }), [setLocale, applyPresentation, getLocale]);
  return <LocaleActionsContext.Provider value={actions}><LocaleContext.Provider value={value}>{children}</LocaleContext.Provider></LocaleActionsContext.Provider>;
}

export function useLocale() {
  const value = useContext(LocaleContext);
  if (value === null) throw new Error("useLocale must be rendered inside LocaleProvider");
  return value;
}

export function useLocaleActions() {
  const value = useContext(LocaleActionsContext);
  if (value === null) throw new Error("useLocaleActions must be rendered inside LocaleProvider");
  return value;
}
