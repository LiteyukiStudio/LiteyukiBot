import { memo, useRef } from "react";
import { Activity, Boxes, Cable, Cog, Languages, Menu, Network, Radio, RefreshCw, SunMoon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLocale, type Locale } from "@/i18n/locale";
import type { Dashboard } from "@/models/dashboard";
import type { Workspace } from "@/models/workspace";
import { cn } from "@/lib/utils";
import { accents, useThemeController, type Accent, type ThemeMode } from "@/themes/theme-controller";

export const navigation: { id: Workspace; labelKey: string; icon: typeof Activity }[] = [
  { id: "overview", labelKey: "webui.nav.overview", icon: Activity },
  { id: "events", labelKey: "webui.nav.events", icon: Radio },
  { id: "topology", labelKey: "webui.nav.topology", icon: Network },
  { id: "runtimes", labelKey: "webui.nav.runtimes", icon: Cable },
  { id: "plugins", labelKey: "webui.nav.plugins", icon: Boxes },
  { id: "configuration", labelKey: "webui.nav.configuration", icon: Cog },
];

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

  return <header className="webui-topbar"><div className="webui-topbar-page"><Button className="lg:hidden" variant="outline" size="icon" onClick={openNavigation} aria-label={t("webui.header.open_navigation")}><Menu /></Button><h1>{pageTitle}</h1></div><div className="webui-topbar-actions"><div className={cn("webui-topbar-state", !ready && "webui-topbar-state--attention")} aria-label={`Kernel ${dashboard.kernelState}`}><span className="webui-status-dot" /><span className="font-medium">{ready ? t("webui.status.ready") : dashboard.kernelState}</span><span className="webui-topbar-runtime-summary">{runtimeSummary}</span></div><DropdownMenu><DropdownMenuTrigger asChild><Button variant="outline" size="icon" aria-label={t("webui.header.language")}><Languages size={16} /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuRadioGroup value={locale} onValueChange={applyLocale}><DropdownMenuRadioItem value="en-US">English</DropdownMenuRadioItem><DropdownMenuRadioItem value="zh-CN">简体中文</DropdownMenuRadioItem></DropdownMenuRadioGroup></DropdownMenuContent></DropdownMenu><DropdownMenu><DropdownMenuTrigger asChild><Button ref={themeButton} variant="outline" size="icon" aria-label={t("webui.header.theme")}><SunMoon size={16} /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuRadioGroup value={mode} onValueChange={applyMode}><DropdownMenuRadioItem value="system">{t("webui.theme.system")}</DropdownMenuRadioItem><DropdownMenuRadioItem value="light">{t("webui.theme.light")}</DropdownMenuRadioItem><DropdownMenuRadioItem value="dark">{t("webui.theme.dark")}</DropdownMenuRadioItem></DropdownMenuRadioGroup><Separator className="my-1" /><DropdownMenuRadioGroup value={accent} onValueChange={applyAccent}>{accents.map((item) => <DropdownMenuRadioItem value={item} key={item}><span className={`webui-theme-swatch webui-theme-swatch--${item}`} />{t(`webui.theme.${item}`)}</DropdownMenuRadioItem>)}</DropdownMenuRadioGroup></DropdownMenuContent></DropdownMenu><Tooltip><TooltipTrigger asChild><Button variant="outline" size="icon" onClick={refresh} aria-label={t("webui.action.refresh")}><RefreshCw size={16} /></Button></TooltipTrigger><TooltipContent>{t("webui.action.refresh")}</TooltipContent></Tooltip></div></header>;
});

export const Sidebar = memo(function Sidebar({ active, dashboard, drawer = false, navigate }: { active: Workspace; dashboard: Dashboard; drawer?: boolean; navigate: (workspace: Workspace) => void }) {
  const { presentation, t } = useLocale();
  const isOverview = active === "overview";
  return <aside className={cn("webui-sidebar h-full min-h-screen flex-col", drawer ? "webui-sidebar--drawer flex" : "hidden lg:flex")}><button type="button" className="webui-sidebar-brand" aria-current={isOverview ? "page" : undefined} onClick={() => { if (!isOverview) navigate("overview"); }}><span className="webui-sidebar-brand-name">{t("webui.app.name")}</span></button><nav className="webui-sidebar-nav">{navigation.map(({ id, labelKey, icon: Icon }) => <Button key={id} variant="ghost" data-active={active === id || undefined} className="webui-sidebar-nav-item" onClick={() => navigate(id)}><Icon size={16} strokeWidth={1.8} />{t(labelKey)}</Button>)}</nav><div className="webui-sidebar-version font-mono">v{dashboard.version}+{presentation?.webuiVersion ?? "-"}</div></aside>;
});
