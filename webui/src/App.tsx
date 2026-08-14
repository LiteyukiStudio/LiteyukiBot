import { useEffect, useState } from "react";
import {
  Activity,
  Boxes,
  Braces,
  Cable,
  CircleAlert,
  Cog,
  Languages,
  Monitor,
  Moon,
  Network,
  Radio,
  Sun,
  type LucideIcon,
} from "lucide-react";

import { type Locale, type MessageKey, messages, resolveLocale } from "./i18n/messages";

type Workspace = "overview" | "events" | "topology" | "runtimes" | "plugins" | "functions" | "configuration";
type Theme = "system" | "light" | "dark";

const navigation: ReadonlyArray<{ id: Workspace; label: MessageKey; icon: LucideIcon }> = [
  { id: "overview", label: "nav.overview", icon: Activity },
  { id: "events", label: "nav.events", icon: Radio },
  { id: "topology", label: "nav.topology", icon: Network },
  { id: "runtimes", label: "nav.runtimes", icon: Cable },
  { id: "plugins", label: "nav.plugins", icon: Boxes },
  { id: "functions", label: "nav.functions", icon: Braces },
  { id: "configuration", label: "nav.configuration", icon: Cog },
];

const workspaceLabels: Record<Workspace, MessageKey> = Object.fromEntries(
  navigation.map(({ id, label }) => [id, label]),
) as Record<Workspace, MessageKey>;

function readPreference(key: string, fallback: string): string {
  const value = window.localStorage.getItem(key);
  return value ?? fallback;
}

export function App() {
  const [locale, setLocale] = useState<Locale>(() => resolveLocale(readPreference("liteyuki.locale", "en-US")));
  const [theme, setTheme] = useState<Theme>(() => readPreference("liteyuki.theme", "system") as Theme);
  const [workspace, setWorkspace] = useState<Workspace>("overview");
  const t = (key: MessageKey) => messages[locale][key];

  useEffect(() => {
    window.localStorage.setItem("liteyuki.locale", locale);
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    window.localStorage.setItem("liteyuki.theme", theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const cycleTheme = () => {
    setTheme((current) => (current === "system" ? "light" : current === "light" ? "dark" : "system"));
  };
  const ThemeIcon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label={t("app.name")}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <div>
            <strong>{t("app.name")}</strong>
            <span>{t("app.subtitle")}</span>
          </div>
        </div>
        <nav className="navigation" aria-label={t("app.name")}>
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              className={workspace === id ? "nav-item nav-item-active" : "nav-item"}
              key={id}
              onClick={() => setWorkspace(id)}
              type="button"
            >
              <Icon aria-hidden="true" size={18} strokeWidth={1.75} />
              <span>{t(label)}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-status">
          <span className="status-dot" aria-hidden="true" />
          <span>{t("health.unavailable")}</span>
        </div>
      </aside>

      <section className="workbench">
        <header className="topbar">
          <div>
            <p className="eyebrow">{t("header.local")}</p>
            <h1>{t(workspace === "overview" ? "overview.title" : workspaceLabels[workspace])}</h1>
          </div>
          <div className="toolbar">
            <button className="icon-button" onClick={() => setLocale(locale === "en-US" ? "zh-CN" : "en-US")} type="button">
              <Languages aria-hidden="true" size={18} />
              <span className="sr-only">{t("header.language")}</span>
            </button>
            <button className="icon-button" onClick={cycleTheme} type="button">
              <ThemeIcon aria-hidden="true" size={18} />
              <span className="sr-only">{t("header.theme")}: {t(`theme.${theme}` as MessageKey)}</span>
            </button>
          </div>
        </header>

        {workspace === "overview" ? <Overview t={t} /> : <WorkspaceEmpty t={t} />}
      </section>
    </main>
  );
}

function Overview({ t }: { t: (key: MessageKey) => string }) {
  return (
    <div className="content-grid">
      <section className="status-strip" aria-live="polite">
        <CircleAlert aria-hidden="true" size={20} />
        <div>
          <strong>{t("health.unavailable")}</strong>
          <p>{t("health.unavailableDetail")}</p>
        </div>
        <span className="fault-count">0 {t("health.faults")}</span>
      </section>
      <section className="ledger-panel">
        <PanelHeading label={t("overview.ledger")} />
        <EmptyMessage>{t("overview.ledgerEmpty")}</EmptyMessage>
      </section>
      <section className="side-panel">
        <PanelHeading label={t("overview.runtimeHealth")} />
        <EmptyMessage>{t("overview.runtimeEmpty")}</EmptyMessage>
      </section>
      <section className="side-panel">
        <PanelHeading label={t("overview.evidence")} />
        <EmptyMessage>{t("overview.evidenceEmpty")}</EmptyMessage>
      </section>
    </div>
  );
}

function WorkspaceEmpty({ t }: { t: (key: MessageKey) => string }) {
  return (
    <section className="workspace-empty">
      <Radio aria-hidden="true" size={28} strokeWidth={1.5} />
      <h2>{t("workspace.emptyTitle")}</h2>
      <p>{t("workspace.emptyDetail")}</p>
    </section>
  );
}

function PanelHeading({ label }: { label: string }) {
  return <h2 className="panel-heading">{label}</h2>;
}

function EmptyMessage({ children }: { children: string }) {
  return <p className="empty-message">{children}</p>;
}
