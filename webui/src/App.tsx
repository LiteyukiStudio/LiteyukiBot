import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity, ArrowRight, Boxes, Braces, Cable, Check, ChevronRight, CircleAlert, CircleCheck,
  CircleDot, CirclePause, Cog, ExternalLink, Languages, Menu, Moon, Network, Play, Plus,
  Radio, RotateCcw, Search, ShieldCheck, SlidersHorizontal, Sun, X, type LucideIcon,
} from "lucide-react";

import { type Locale, type MessageKey, messages, resolveLocale } from "./i18n/messages";
import {
  functions, ledger, operations, plugins, runtimes,
  type DetailReference, type Operation, type PluginComponent, type Severity, type Workspace,
} from "./model";

type Theme = "system" | "light" | "dark";
type Accent = "blue" | "lilac" | "teal";

const navigation: ReadonlyArray<{ id: Workspace; label: MessageKey; icon: LucideIcon }> = [
  { id: "overview", label: "nav.overview", icon: Activity }, { id: "events", label: "nav.events", icon: Radio },
  { id: "topology", label: "nav.topology", icon: Network }, { id: "runtimes", label: "nav.runtimes", icon: Cable },
  { id: "plugins", label: "nav.plugins", icon: Boxes }, { id: "functions", label: "nav.functions", icon: Braces },
  { id: "configuration", label: "nav.configuration", icon: Cog },
];

const workspaceLabels = Object.fromEntries(navigation.map(({ id, label }) => [id, label])) as Record<Workspace, MessageKey>;

function readPreference(key: string, fallback: string): string {
  return window.localStorage.getItem(key) ?? fallback;
}

function parseLocation(): { workspace: Workspace; detail: DetailReference | null } {
  const parts = window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const workspace = navigation.some(({ id }) => id === parts[0]) ? (parts[0] as Workspace) : "overview";
  const kind = workspace === "events" ? "event" : workspace === "runtimes" ? "runtime" : workspace === "plugins" ? "plugin" : workspace === "functions" ? "function" : null;
  return { workspace, detail: kind && parts[1] ? { kind, id: parts[1] } : null };
}

function routeFor(workspace: Workspace, detail?: DetailReference | null): string {
  return `#/${workspace}${detail ? `/${detail.id}` : ""}`;
}

export function App() {
  const [location, setLocation] = useState(parseLocation);
  const [locale, setLocale] = useState<Locale>(() => resolveLocale(readPreference("liteyuki.locale", "en-US")));
  const [theme, setTheme] = useState<Theme>(() => readPreference("liteyuki.theme", "system") as Theme);
  const [accent, setAccent] = useState<Accent>(() => readPreference("liteyuki.accent", "blue") as Accent);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [setupVisible, setSetupVisible] = useState(() => new URLSearchParams(window.location.search).has("setup"));
  const t = (key: MessageKey) => messages[locale][key];

  useEffect(() => {
    const onHash = () => setLocation(parseLocation());
    window.addEventListener("hashchange", onHash);
    if (!window.location.hash) window.location.replace(routeFor("overview"));
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    const match = /^#ticket=([^&]+)$/.exec(window.location.hash);
    if (!match) return;
    const ticket = decodeURIComponent(match[1]);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${routeFor("overview")}`);
    setLocation(parseLocation());
    void fetch("/api/v1/session", {
      method: "POST",
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ticket }),
    });
  }, []);
  useEffect(() => { window.localStorage.setItem("liteyuki.locale", locale); document.documentElement.lang = locale; }, [locale]);
  useEffect(() => { window.localStorage.setItem("liteyuki.theme", theme); document.documentElement.dataset.theme = theme; }, [theme]);
  useEffect(() => { window.localStorage.setItem("liteyuki.accent", accent); document.documentElement.dataset.accent = accent; }, [accent]);

  const navigate = (workspace: Workspace, detail?: DetailReference | null) => {
    window.location.hash = routeFor(workspace, detail);
    setMobileMenu(false);
  };
  const cycleTheme = () => setTheme((current) => current === "system" ? "light" : current === "light" ? "dark" : "system");
  const ThemeIcon = theme === "dark" ? Moon : theme === "light" ? Sun : SlidersHorizontal;

  if (setupVisible) return <SetupScreen t={t} onComplete={() => setSetupVisible(false)} />;
  return (
    <main className="app-shell">
      <Sidebar active={location.workspace} mobileOpen={mobileMenu} t={t} onNavigate={navigate} />
      <section className="workbench">
        <header className="topbar">
          <button className="icon-button mobile-menu" type="button" aria-label={t("header.openMenu")} onClick={() => setMobileMenu(true)}><Menu size={18} /></button>
          <div className="page-title"><p className="eyebrow">{t("app.local")}</p><h1>{t(workspaceLabels[location.workspace])}</h1><p>{location.workspace === "overview" ? t("overview.summary") : t(`${location.workspace}.summary` as MessageKey)}</p></div>
          <div className="toolbar">
            <AccentMenu accent={accent} t={t} onChange={setAccent} />
            <button className="icon-button" type="button" aria-label={t("header.language")} onClick={() => setLocale(locale === "en-US" ? "zh-CN" : "en-US")}><Languages size={18} /></button>
            <button className="icon-button" type="button" aria-label={`${t("header.theme")}: ${t(`theme.${theme}` as MessageKey)}`} onClick={cycleTheme}><ThemeIcon size={18} /></button>
          </div>
        </header>
        <WorkspaceView workspace={location.workspace} t={t} onNavigate={navigate} onOperation={setOperation} />
      </section>
      {mobileMenu && <MobileScrim label={t("drawer.close")} onClose={() => setMobileMenu(false)} />}
      {location.detail && <DetailDrawer detail={location.detail} t={t} onClose={() => navigate(location.workspace)} onOperation={setOperation} />}
      {operation && <OperationDialog operation={operation} t={t} onClose={() => setOperation(null)} />}
    </main>
  );
}

function Sidebar({ active, mobileOpen, t, onNavigate }: { active: Workspace; mobileOpen: boolean; t: T; onNavigate: (workspace: Workspace) => void }) {
  return <aside className={mobileOpen ? "sidebar sidebar-mobile-open" : "sidebar"} aria-label={t("app.name")}>
    <div className="brand"><span className="brand-mark" aria-hidden="true" /><div><strong>{t("app.name")}</strong><span>{t("app.subtitle")}</span></div></div>
    <nav className="navigation" aria-label={t("app.name")}>{navigation.map(({ id, label, icon: Icon }) => <button className={active === id ? "nav-item nav-item-active" : "nav-item"} key={id} onClick={() => onNavigate(id)} type="button"><Icon aria-hidden="true" size={18} strokeWidth={1.8} /><span>{t(label)}</span></button>)}</nav>
    <div className="sidebar-status"><span className="status-dot" aria-hidden="true" /><span>{t("status.healthy")}</span><span className="sidebar-instance">local</span></div>
  </aside>;
}

type T = (key: MessageKey) => string;

function WorkspaceView({ workspace, t, onNavigate, onOperation }: { workspace: Workspace; t: T; onNavigate: (workspace: Workspace, detail?: DetailReference) => void; onOperation: (operation: Operation) => void }) {
  if (workspace === "overview") return <Overview t={t} onNavigate={onNavigate} onOperation={onOperation} />;
  if (workspace === "events") return <Events t={t} onNavigate={onNavigate} />;
  if (workspace === "topology") return <Topology t={t} onNavigate={onNavigate} />;
  if (workspace === "runtimes") return <Runtimes t={t} onNavigate={onNavigate} onOperation={onOperation} />;
  if (workspace === "plugins") return <Plugins t={t} onNavigate={onNavigate} onOperation={onOperation} />;
  if (workspace === "functions") return <Functions t={t} onNavigate={onNavigate} />;
  return <Configuration t={t} />;
}

function Overview({ t, onNavigate, onOperation }: { t: T; onNavigate: (workspace: Workspace, detail?: DetailReference) => void; onOperation: (operation: Operation) => void }) {
  return <div className="overview-layout">
    <section className="health-strip"><CircleCheck size={19} aria-hidden="true" /><strong>{t("status.healthy")}</strong><span>{t("overview.activeRuntimes")}: 2 / 3</span><span>{t("overview.eventRate")}: 128/min</span><button type="button" className="quiet-button" onClick={() => onOperation(operations[0])}>{t("overview.openOperation")}<Plus size={15} /></button></section>
    <section className="metric-row"><Metric label={t("overview.activeRuntimes")} value="2" trend="3 configured" /><Metric label={t("overview.enabledPlugins")} value="2" trend="3 installed" /><Metric label={t("overview.eventRate")} value="128" trend="events / min" /><Metric label={t("overview.faults")} value="1" trend="delivery delay" tone="attention" /></section>
    <Panel className="ledger-panel" title={t("overview.ledger")} action={<button className="text-button" type="button" onClick={() => onNavigate("events")}>{t("overview.allEvents")}<ArrowRight size={15} /></button>}><LedgerTable t={t} items={ledger.slice(0, 4)} onOpen={(id) => onNavigate("events", { kind: "event", id })} /></Panel>
    <Panel className="runtime-panel" title={t("overview.runtime")}><RuntimeList t={t} compact onOpen={(id) => onNavigate("runtimes", { kind: "runtime", id })} /></Panel>
    <Panel className="evidence-panel" title={t("overview.evidence")}><div className="evidence"><CircleAlert size={18} /><div><strong>{ledger[2].title}</strong><span>{ledger[2].source} · {ledger[2].at}</span></div><ChevronRight size={16} /></div></Panel>
  </div>;
}

function Events({ t, onNavigate }: { t: T; onNavigate: (workspace: Workspace, detail?: DetailReference) => void }) {
  const [filter, setFilter] = useState("");
  const records = useMemo(() => ledger.filter((item) => `${item.title} ${item.source} ${item.trace}`.toLowerCase().includes(filter.toLowerCase())), [filter]);
  return <div className="workspace-stack"><section className="filter-bar"><label className="search-field"><Search size={16} /><span className="sr-only">{t("events.filter")}</span><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder={t("events.filterPlaceholder")} /></label><span className="record-count">{records.length} {t("events.all")}</span></section><Panel title={t("events.title")}><LedgerTable t={t} items={records} onOpen={(id) => onNavigate("events", { kind: "event", id })} />{records.length === 0 && <EmptyState label={t("events.empty")} />}</Panel></div>;
}

function Topology({ t, onNavigate }: { t: T; onNavigate: (workspace: Workspace, detail?: DetailReference) => void }) {
  return <div className="topology-grid"><Panel title={t("topology.kernel")}><div className="topology-node kernel-node"><ShieldCheck size={19} /><div><strong>liteyuki.core</strong><span>{t("status.healthy")}</span></div></div></Panel><Panel title={t("topology.runtime")}><div className="node-list">{runtimes.map((runtime) => <button key={runtime.id} className="topology-node" onClick={() => onNavigate("runtimes", { kind: "runtime", id: runtime.id })}><Cable size={18} /><div><strong>{runtime.id}</strong><span>{runtime.protocol}</span></div><StateBadge value={runtime.state} t={t} /></button>)}</div></Panel><Panel title={t("topology.plugin")}><div className="node-list">{plugins.filter((plugin) => plugin.state === "enabled").map((plugin) => <button key={plugin.id} className="topology-node" onClick={() => onNavigate("plugins", { kind: "plugin", id: plugin.id })}><Boxes size={18} /><div><strong>{plugin.name}</strong><span>{plugin.version}</span></div><StateBadge value={plugin.state} t={t} /></button>)}</div></Panel><Panel title={t("topology.route")}><EmptyState label={t("topology.noRoutes")} /></Panel></div>;
}

function Runtimes({ t, onNavigate, onOperation }: { t: T; onNavigate: (workspace: Workspace, detail?: DetailReference) => void; onOperation: (operation: Operation) => void }) {
  return <Panel title={t("runtimes.title")} action={<button className="quiet-button" type="button" onClick={() => onOperation(operations[0])}>{t("overview.openOperation")}<Plus size={15} /></button>}><div className="data-table runtime-table"><div className="table-row table-header"><span>{t("runtimes.runtime")}</span><span>{t("runtimes.kind")}</span><span>{t("common.state")}</span><span>{t("runtimes.activity")}</span><span /></div>{runtimes.map((runtime) => <div className="table-row" key={runtime.id}><button className="entity-button" onClick={() => onNavigate("runtimes", { kind: "runtime", id: runtime.id })}><span className="entity-icon"><Cable size={16} /></span><strong>{runtime.id}</strong></button><span>{runtime.kind}</span><StateBadge value={runtime.state} t={t} /><span className="muted">{runtime.activity}</span><button className="row-open" aria-label={`${t("common.open")} ${runtime.id}`} onClick={() => onNavigate("runtimes", { kind: "runtime", id: runtime.id })}><ChevronRight size={17} /></button></div>)}</div></Panel>;
}

function Plugins({ t, onNavigate, onOperation }: { t: T; onNavigate: (workspace: Workspace, detail?: DetailReference) => void; onOperation: (operation: Operation) => void }) {
  const profile = plugins[0];
  return <div className="workspace-stack"><Panel title={t("plugins.title")}><div className="data-table plugin-table"><div className="table-row table-header"><span>{t("plugins.plugin")}</span><span>{t("plugins.version")}</span><span>{t("common.state")}</span><span>{t("plugins.capabilities")}</span><span /></div>{plugins.map((plugin) => <div className="table-row" key={plugin.id}><button className="entity-button" onClick={() => onNavigate("plugins", { kind: "plugin", id: plugin.id })}><span className="entity-icon"><Boxes size={16} /></span><strong>{plugin.name}</strong></button><span>{plugin.version}</span><StateBadge value={plugin.state} t={t} /><span className="capability-cell">{plugin.capabilities.join(", ")}</span><button className="row-open" aria-label={`${t("common.open")} ${plugin.name}`} onClick={() => onNavigate("plugins", { kind: "plugin", id: plugin.id })}><ChevronRight size={17} /></button></div>)}</div></Panel>{profile.surface && <PluginSurfaceView surface={profile.surface.components} title={profile.surface.title} t={t} onOperation={onOperation} />}</div>;
}

function Functions({ t, onNavigate }: { t: T; onNavigate: (workspace: Workspace, detail?: DetailReference) => void }) {
  return <Panel title={t("functions.title")}><div className="data-table function-table"><div className="table-row table-header"><span>{t("functions.function")}</span><span>{t("functions.source")}</span><span>{t("functions.handlers")}</span><span>{t("functions.diagnostics")}</span><span /></div>{functions.map((item) => <div className="table-row" key={item.id}><button className="entity-button" onClick={() => onNavigate("functions", { kind: "function", id: item.id })}><span className="entity-icon"><Braces size={16} /></span><strong>{item.id}</strong></button><span className="mono muted">{item.source}</span><span>{item.handlers}</span><StateBadge value={item.state} t={t} /><button className="row-open" aria-label={`${t("common.open")} ${item.id}`} onClick={() => onNavigate("functions", { kind: "function", id: item.id })}><ChevronRight size={17} /></button></div>)}</div></Panel>;
}

function Configuration({ t }: { t: T }) {
  return <div className="config-layout"><Panel title={t("configuration.title")}><dl className="settings-list"><Setting label={t("configuration.version")} value="4" /><Setting label={t("configuration.webui")} value="on_demand" /><Setting label={t("configuration.mode")} value="loopback" /><Setting label={t("configuration.data")} value=".liteyuki/instances/default" mono /></dl></Panel><p className="read-only-note"><ShieldCheck size={17} />{t("configuration.review")}</p></div>;
}

function PluginSurfaceView({ surface, title, t, onOperation }: { surface: PluginComponent[]; title: string; t: T; onOperation: (operation: Operation) => void }) {
  return <Panel title={title} action={<span className="surface-label">{t("plugins.surface")}</span>}><div className="plugin-surface">{surface.map((component) => <PluginComponentView component={component} key={component.id} t={t} onOperation={onOperation} />)}</div></Panel>;
}

function PluginComponentView({ component, t, onOperation }: { component: PluginComponent; t: T; onOperation: (operation: Operation) => void }) {
  if (component.kind === "metric") return <div className="surface-metric"><span>{component.label}</span><strong>{component.value}</strong></div>;
  if (component.kind === "table") return <div className="surface-table"><h3>{component.label}</h3><div className="surface-table-head">{component.columns?.map((item) => <span key={item}>{item}</span>)}</div>{component.rows?.map((row) => <div className="surface-table-row" key={row[0]}>{row.map((item) => <span key={item}>{item}</span>)}</div>)}</div>;
  if (component.kind === "operation_form") return <div className="surface-action"><div><strong>{component.label}</strong><span>{component.operationId}</span></div><button className="quiet-button" type="button" onClick={() => onOperation({ id: component.operationId ?? component.id, label: component.label, description: t("operation.summary"), target: "profile", impact: "standard" })}>{t("common.open")}<ExternalLink size={15} /></button></div>;
  return <div className="surface-notice">{component.label}</div>;
}

function DetailDrawer({ detail, t, onClose, onOperation }: { detail: DetailReference; t: T; onClose: () => void; onOperation: (operation: Operation) => void }) {
  const item = detail.kind === "event" ? ledger.find((candidate) => candidate.id === detail.id) : detail.kind === "runtime" ? runtimes.find((candidate) => candidate.id === detail.id) : detail.kind === "plugin" ? plugins.find((candidate) => candidate.id === detail.id) : functions.find((candidate) => candidate.id === detail.id);
  const runtimeItem = detail.kind === "runtime" ? runtimes.find((candidate) => candidate.id === detail.id) : undefined;
  const pluginItem = detail.kind === "plugin" ? plugins.find((candidate) => candidate.id === detail.id) : undefined;
  const functionItem = detail.kind === "function" ? functions.find((candidate) => candidate.id === detail.id) : undefined;
  if (!item) return null;
  const title = detail.kind === "event" ? t("events.detail") : detail.kind === "runtime" ? t("runtimes.detail") : detail.kind === "plugin" ? t("plugins.detail") : t("functions.detail");
  return <div className="drawer-layer"><button type="button" aria-label={t("drawer.close")} className="drawer-scrim" onClick={onClose} /><aside className="drawer" aria-label={title}><header><div><p className="eyebrow">{title}</p><h2>{"title" in item ? item.title : "name" in item ? item.name : item.id}</h2></div><button className="icon-button" type="button" aria-label={t("drawer.close")} onClick={onClose}><X size={18} /></button></header><div className="drawer-content"><DetailRow label={t("detail.id")} value={item.id} mono />{"state" in item && <DetailRow label={t("detail.status")} value={t(`status.${item.state}` as MessageKey)} />} {"source" in item && <DetailRow label={t("detail.source")} value={item.source} />} {"trace" in item && <DetailRow label={t("detail.trace")} value={item.trace} mono />} {"detail" in item && <section className="detail-section"><h3>{t("detail.evidence")}</h3><p>{item.detail}</p></section>} {runtimeItem && <><DetailRow label={t("runtimes.protocol")} value={runtimeItem.protocol} /><DetailRow label={t("runtimes.capabilities")} value={String(runtimeItem.capabilityCount)} /><button className="primary-button" type="button" onClick={() => onOperation(runtimeItem.id === "satori-edge" ? operations[1] : operations[0])}>{t("runtimes.actions")}<ArrowRight size={16} /></button></>} {pluginItem && <><DetailRow label={t("plugins.version")} value={pluginItem.version} /><DetailRow label={t("plugins.capabilities")} value={pluginItem.capabilities.join(", ")} /><button className="primary-button" type="button" onClick={() => onOperation(operations[2])}>{t("plugins.operations")}<ArrowRight size={16} /></button></>} {functionItem && <><DetailRow label={t("functions.source")} value={functionItem.source} mono /><DetailRow label={t("functions.diagnostics")} value={functionItem.diagnostics} /><p className="read-only-note"><ShieldCheck size={17} />{t("functions.readOnly")}</p></>}</div></aside></div>;
}

function OperationDialog({ operation, t, onClose }: { operation: Operation; t: T; onClose: () => void }) {
  const [confirmation, setConfirmation] = useState(""); const [queued, setQueued] = useState(false); const needsConfirmation = operation.impact === "high";
  return <div className="dialog-layer" role="presentation"><button className="drawer-scrim" aria-label={t("operation.close")} onClick={onClose} /><section className="dialog" role="dialog" aria-modal="true" aria-labelledby="operation-title"><button className="icon-button dialog-close" type="button" aria-label={t("operation.close")} onClick={onClose}><X size={18} /></button>{queued ? <div className="success-state"><CircleCheck size={30} /><h2>{t("operation.queued")}</h2><p>{t("operation.queuedDetail")}</p><button className="primary-button" type="button" onClick={onClose}>{t("common.close")}</button></div> : <><p className="eyebrow">{operation.impact === "high" ? t("operation.highImpact") : t("operation.standard")}</p><h2 id="operation-title">{operation.label}</h2><p className="dialog-summary">{operation.description}</p><DetailRow label={t("operation.target")} value={operation.target} mono />{needsConfirmation && <label className="confirm-field"><span>{t("operation.confirm")}</span><input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder={t("operation.confirmHint")} /></label>}<div className="dialog-actions"><button className="text-button" type="button" onClick={onClose}>{t("operation.cancel")}</button><button className="primary-button" type="button" disabled={needsConfirmation && confirmation !== operation.target} onClick={() => setQueued(true)}>{t("operation.submit")}<ArrowRight size={16} /></button></div></>}</section></div>;
}

function SetupScreen({ t, onComplete }: { t: T; onComplete: () => void }) {
  const [runtime, setRuntime] = useState("onebot"); const [source, setSource] = useState("");
  return <main className="setup-shell"><section className="setup-panel"><div className="brand"><span className="brand-mark" /><div><strong>{t("app.name")}</strong><span>{t("app.subtitle")}</span></div></div><div className="setup-copy"><p className="eyebrow">{t("app.local")}</p><h1>{t("setup.title")}</h1><p>{t("setup.summary")}</p></div><label className="setup-field"><span>{t("setup.runtime")}</span><select value={runtime} onChange={(event) => setRuntime(event.target.value)}><option value="onebot">OneBot</option><option value="satori">Satori</option><option value="nonebot">NoneBot</option></select></label><label className="setup-field"><span>{t("setup.pluginSource")}</span><input value={source} onChange={(event) => setSource(event.target.value)} placeholder="https://example.invalid/plugin" /></label><p className="setup-ready"><Check size={16} />{t("setup.ready")}</p><div className="setup-actions"><button className="text-button" type="button" onClick={onComplete}>{t("setup.skip")}</button><button className="primary-button" type="button" onClick={onComplete}>{t("setup.create")}<ArrowRight size={16} /></button></div></section></main>;
}

function AccentMenu({ accent, t, onChange }: { accent: Accent; t: T; onChange: (accent: Accent) => void }) { return <div className="accent-menu" aria-label={t("header.accent")}>{(["blue", "lilac", "teal"] as Accent[]).map((item) => <button className={accent === item ? "accent-swatch accent-selected" : "accent-swatch"} type="button" key={item} aria-label={t(`accent.${item}` as MessageKey)} onClick={() => onChange(item)}><span className={`swatch-fill swatch-${item}`} /></button>)}</div>; }
function Panel({ title, action, className = "", children }: { title: string; action?: ReactNode; className?: string; children: ReactNode }) { return <section className={`panel ${className}`}><header className="panel-header"><h2>{title}</h2>{action}</header>{children}</section>; }
function Metric({ label, value, trend, tone }: { label: string; value: string; trend: string; tone?: Severity }) { return <section className={tone ? `metric metric-${tone}` : "metric"}><span>{label}</span><strong>{value}</strong><small>{trend}</small></section>; }
function StateBadge({ value, t }: { value: string; t: T }) { const icon = value === "running" || value === "enabled" || value === "ready" ? <CircleCheck size={14} /> : value === "recovering" || value === "attention" ? <CircleDot size={14} /> : <CirclePause size={14} />; return <span className={`state-badge state-${value}`}>{icon}{t(`status.${value}` as MessageKey)}</span>; }
function LedgerTable({ t, items, onOpen }: { t: T; items: typeof ledger; onOpen: (id: string) => void }) { return <div className="data-table ledger-table"><div className="table-row table-header"><span>{t("events.time")}</span><span>{t("common.action")}</span><span>{t("events.source")}</span><span>{t("events.trace")}</span><span /></div>{items.map((item) => <div className="table-row" key={item.id}><span className="mono muted">{item.at}</span><button className="ledger-title" onClick={() => onOpen(item.id)}><StateBadge value={item.status} t={t} /><strong>{item.title}</strong></button><span>{item.source}</span><span className="mono muted">{item.trace}</span><button className="row-open" aria-label={`${t("common.open")} ${item.title}`} onClick={() => onOpen(item.id)}><ChevronRight size={17} /></button></div>)}</div>; }
function RuntimeList({ t, compact, onOpen }: { t: T; compact?: boolean; onOpen: (id: string) => void }) { return <div className={compact ? "runtime-list compact" : "runtime-list"}>{runtimes.map((runtime) => <button className="runtime-list-item" key={runtime.id} onClick={() => onOpen(runtime.id)}><span className="entity-icon"><Cable size={16} /></span><span><strong>{runtime.id}</strong><small>{runtime.kind} · {runtime.activity}</small></span><StateBadge value={runtime.state} t={t} /></button>)}</div>; }
function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) { return <div className="detail-row"><span>{label}</span><strong className={mono ? "mono" : ""}>{value}</strong></div>; }
function Setting({ label, value, mono }: { label: string; value: string; mono?: boolean }) { return <div><dt>{label}</dt><dd className={mono ? "mono" : ""}>{value}</dd></div>; }
function EmptyState({ label }: { label: string }) { return <div className="empty-state"><CirclePause size={19} /><span>{label}</span></div>; }
function MobileScrim({ label, onClose }: { label: string; onClose: () => void }) { return <button className="mobile-scrim" aria-label={label} onClick={onClose} />; }
