import { memo, useRef, useState } from "react";
import { Activity, Boxes, Bug, Cable, Cog, FileCode2, FileText, Languages, Menu, Network, Radio, RefreshCw, Search, SunMoon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLocale, type Locale } from "@/i18n/locale";
import type { Dashboard } from "@/models/dashboard";
import type { Workspace } from "@/models/workspace";
import type { WebUiLayout } from "@/models/api";
import { cn } from "@/lib/utils";
import { accents, useThemeController, type Accent, type ThemeMode } from "@/themes/theme-controller";

export const navigation: { id: Workspace; labelKey: string; icon: typeof Activity }[] = [
  { id: "overview", labelKey: "webui.nav.overview", icon: Activity },
  { id: "logs", labelKey: "webui.nav.logs", icon: FileText },
  { id: "events", labelKey: "webui.nav.events_short", icon: Radio },
  { id: "topology", labelKey: "webui.nav.topology", icon: Network },
  { id: "runtimes", labelKey: "webui.nav.runtimes", icon: Cable },
  { id: "plugins", labelKey: "webui.nav.plugins", icon: Boxes },
  { id: "lyf", labelKey: "webui.nav.lyf", icon: FileCode2 },
  { id: "configuration", labelKey: "webui.nav.about", icon: Cog },
  { id: "developer", labelKey: "webui.nav.developer", icon: Bug },
];

/**
 * Renders current kernel health plus locale, theme, navigation, and refresh controls.
 * @param props - Dashboard state, active workspace, and shell command callbacks.
 * @returns The memoized top status bar.
 */
export const TopStatusBar = memo(function TopStatusBar({ dashboard, workspace, openNavigation, refresh }: { dashboard: Dashboard; workspace: Workspace; openNavigation: () => void; refresh: () => void }) {
  const { locale, setLocale, t } = useLocale();
  const { accent, mode, setAccent, setMode } = useThemeController();
  const themeButton = useRef<HTMLButtonElement>(null);
  const ready = dashboard.kernelState === "ready";
  const activeRuntimes = dashboard.runtimes.filter((runtime) => runtime.state === "ready").length;
  const runtimeSummary = t("webui.status.runtimes", { active: activeRuntimes, total: dashboard.runtimes.length });
  const pageTitle = t(navigation.find((entry) => entry.id === workspace)?.labelKey ?? "webui.nav.overview");
  const applyLocale = (value: string) => { if (value === "en-US" || value === "zh-CN") setLocale(value as Locale); };
  const applyAccent = (value: string) => { if (accents.includes(value as Accent)) setAccent(value as Accent); };
  const applyMode = (value: string) => { if (["system", "light", "dark"].includes(value)) setMode(value as ThemeMode, themeButton.current); };

  return <header className="webui-topbar"><div className="webui-topbar-page"><Button className="lg:hidden" variant="outline" size="icon" onClick={openNavigation} aria-label={t("webui.header.open_navigation")}><Menu /></Button><h1>{pageTitle}</h1></div><div className="webui-topbar-actions"><div className={cn("webui-topbar-state", !ready && "webui-topbar-state--attention")} aria-label={t("webui.status.kernel", { state: dashboard.kernelState })}><span className="webui-status-dot" /><span className="font-medium">{ready ? t("webui.status.ready") : t(`webui.state.${dashboard.kernelState}`)}</span><span className="webui-topbar-runtime-summary">{runtimeSummary}</span></div><DropdownMenu><DropdownMenuTrigger asChild><Button variant="outline" size="icon" aria-label={t("webui.header.language")}><Languages size={16} /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuRadioGroup value={locale} onValueChange={applyLocale}><DropdownMenuRadioItem value="en-US">{t("webui.locale.en-US")}</DropdownMenuRadioItem><DropdownMenuRadioItem value="zh-CN">{t("webui.locale.zh-CN")}</DropdownMenuRadioItem></DropdownMenuRadioGroup></DropdownMenuContent></DropdownMenu><DropdownMenu><DropdownMenuTrigger asChild><Button ref={themeButton} variant="outline" size="icon" aria-label={t("webui.header.theme")}><SunMoon size={16} /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuRadioGroup value={mode} onValueChange={applyMode}><DropdownMenuRadioItem value="system">{t("webui.theme.system")}</DropdownMenuRadioItem><DropdownMenuRadioItem value="light">{t("webui.theme.light")}</DropdownMenuRadioItem><DropdownMenuRadioItem value="dark">{t("webui.theme.dark")}</DropdownMenuRadioItem></DropdownMenuRadioGroup><Separator className="my-1" /><DropdownMenuRadioGroup value={accent} onValueChange={applyAccent}>{accents.map((item) => <DropdownMenuRadioItem value={item} key={item}><span className={`webui-theme-swatch webui-theme-swatch--${item}`} />{t(`webui.theme.${item}`)}</DropdownMenuRadioItem>)}</DropdownMenuRadioGroup></DropdownMenuContent></DropdownMenu><Tooltip><TooltipTrigger asChild><Button variant="outline" size="icon" onClick={refresh} aria-label={t("webui.action.refresh")}><RefreshCw size={16} /></Button></TooltipTrigger><TooltipContent>{t("webui.action.refresh")}</TooltipContent></Tooltip></div></header>;
});

/**
 * Renders primary workspace navigation for either desktop or drawer placement.
 * @param props - Active route, dashboard metadata, placement mode, and navigation callback.
 * @returns The memoized sidebar navigation surface.
 */
export const Sidebar = memo(function Sidebar({ active, dashboard, drawer = false, navigate, layout }: { active: Workspace; dashboard: Dashboard; drawer?: boolean; navigate: (workspace: Workspace) => void; layout: WebUiLayout }) {
  const { presentation, t } = useLocale();
  const [query, setQuery] = useState("");
  const visibleNavigation = navigation.filter(({ labelKey }) => !drawer || !query.trim() || t(labelKey).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const pluginSubmenu = <>{["discover", "index", "managed", "hosted", "followed"].map((item) => <Button key={item} variant="ghost" className={cn("webui-sidebar-control webui-sidebar-subitem", item === "discover" && "webui-sidebar-select")} data-active={item === "discover" || undefined} onClick={() => window.dispatchEvent(new CustomEvent("liteyuki:plugin-tab", { detail: item }))}>{t(`webui.plugins.${item}`)}</Button>)}</>;
  return <aside className={cn("webui-sidebar h-full min-h-screen flex-col", drawer ? "webui-sidebar--drawer flex" : "hidden lg:flex")}><button type="button" className="webui-sidebar-brand" onClick={() => window.dispatchEvent(new Event("liteyuki:open-navigation"))}><span className="webui-sidebar-brand-name">{t("webui.app.name")}</span></button>{drawer ? <label className="webui-sidebar-search"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search navigation" /></label> : null}<nav className="webui-sidebar-nav">{visibleNavigation.map(({ id, labelKey, icon: Icon }) => <div key={id}><Button variant="ghost" data-active={active === id || undefined} className="webui-sidebar-nav-item" onClick={() => navigate(id)}><Icon size={16} strokeWidth={1.8} />{t(labelKey)}</Button>{active === id && ((id === "developer" && layout === "main-sidebar") || (id === "plugins" && layout === "main-sidebar") || (drawer && layout === "sidebar" && (id === "developer" || id === "plugins"))) ? <div className={cn("webui-sidebar-submenu-float", id === "plugins" && layout === "main-sidebar" && "webui-sidebar-submenu-float--main", drawer && layout === "sidebar" && "webui-sidebar-submenu-float--right")}>{id === "developer" ? <Button variant="ghost" className="webui-sidebar-subitem webui-sidebar-select" data-active="true">{t("webui.developer.toast_section")}</Button> : pluginSubmenu}</div> : null}</div>)}</nav><div className="webui-sidebar-version font-mono">v{dashboard.version}+{presentation?.webuiVersion ?? "-"}</div></aside>;
});
