import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { messages, resolveLocale, type Locale, type MessageKey } from "@/i18n/messages";

const storageKey = "liteyukibot.webui.locale";

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey) => string;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function initialLocale(): Locale {
  try {
    return resolveLocale(localStorage.getItem(storageKey) ?? navigator.language);
  } catch {
    return "en-US";
  }
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
    try {
      localStorage.setItem(storageKey, locale);
    } catch {
      // Locale selection remains active for the current page.
    }
  }, [locale]);

  const value = useMemo(() => ({ locale, setLocale, t: (key: MessageKey) => messages[locale][key] }), [locale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const value = useContext(LocaleContext);
  if (value === null) throw new Error("useLocale must be rendered inside LocaleProvider");
  return value;
}
