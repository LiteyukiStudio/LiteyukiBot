import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import type { WebUiPresentation } from "@/lib/api";

const storageKey = "liteyukibot.webui.locale";
const supportedLocales = ["en-US", "zh-CN"] as const;

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
  const [locale, setLocale] = useState<Locale>(initialLocale);
  const [presentation, setPresentation] = useState<Presentation | null>(null);

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
    const template = presentation?.messages[key] ?? key;
    return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (placeholder, name: string) => String(values[name] ?? placeholder));
  }, [presentation]);
  const value = useMemo(
    () => ({ locale, setLocale, presentation, applyPresentation, t }),
    [locale, presentation, applyPresentation, t],
  );
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const value = useContext(LocaleContext);
  if (value === null) throw new Error("useLocale must be rendered inside LocaleProvider");
  return value;
}
