import { lazy, memo, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowRight, Boxes, Cable, CircleDot, FileClock, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SurfaceCard } from "@/components/surface-card";
import { useLocale } from "@/i18n/locale";
import { cn } from "@/lib/utils";
import type { EventDeliveryPage, LyfResourcePage, WebUiLayout, WebUiOperation } from "@/models/api";
import type { Dashboard, LedgerView } from "@/models/dashboard";
import type { Workspace } from "@/models/workspace";
import type { WebUiApi } from "@/services/webui-api";
import { PluginWorkspace } from "@/features/plugins/plugin-workspace";

const EventDeliveriesView = lazy(() =>
  import("@/features/event-deliveries/event-deliveries-view").then(({ EventDeliveriesView: View }) => ({ default: View })),
);

const OperationDialog = lazy(() =>
  import("@/features/operations/operation-dialog").then(({ OperationDialog: Dialog }) => ({ default: Dialog })),
);

const LyfResourceView = lazy(() => import("@/features/lyf/lyf-resource-view").then(({ LyfResourceView: View }) => ({ default: View })));
const DeveloperView = lazy(() => import("@/features/developer/developer-view").then(({ DeveloperView: View }) => ({ default: View })));
const LogsView = lazy(() => import("@/features/observability/logs-view").then(({ LogsView: View }) => ({ default: View })));
const TopologyGraphView = lazy(() => import("@/features/observability/topology-graph-view").then(({ TopologyGraphView: View }) => ({ default: View })));

const POSITIVE_STATES = new Set(["ready", "running", "enabled", "healthy", "succeeded"]);
const WARNING_STATES = new Set(["attention", "recovering", "queued", "running"]);

type WorkspaceViewProps = {
  workspace: Workspace;
  dashboard: Dashboard;
  eventDeliveries: EventDeliveryPage;
  lyfResources: LyfResourcePage;
  api: WebUiApi;
  reload: () => Promise<void>;
  reloadEventDeliveries: () => Promise<void>;
  pluginLayout: WebUiLayout;
  setPluginLayout: (layout: WebUiLayout) => void;
  toastDuration: number;
  setToastDuration: (duration: number) => void;
};

/**
 * Selects the active operational workspace and owns the cross-workspace operation dialog.
 * @param props - Active workspace, projected data, API client, and refresh commands.
 * @returns The memoized active workspace with any pending operation overlay.
 */
export const WorkspaceView = memo(function WorkspaceView({ workspace, dashboard, eventDeliveries, lyfResources, api, reload, reloadEventDeliveries, pluginLayout, setPluginLayout, toastDuration, setToastDuration }: WorkspaceViewProps) {
  const [operation, setOperation] = useState<WebUiOperation | null>(null);
  const openOperation = useCallback((next: WebUiOperation) => setOperation(next), []);
  const closeOperation = useCallback(() => setOperation(null), []);

  const content = workspace === "overview" ? <Overview dashboard={dashboard} />
    : workspace === "logs" ? <Suspense fallback={<div className="min-h-[382px]" />}><LogsView api={api} /></Suspense>
    : workspace === "events" ? <><EventSummary api={api} /><Suspense fallback={<div className="min-h-[382px]" />}><EventDeliveriesView initial={eventDeliveries} api={api} reloadInitial={reloadEventDeliveries} /></Suspense></>
      : workspace === "topology" ? <Suspense fallback={<div className="min-h-[382px]" />}><TopologyGraphView api={api} /></Suspense>
        : workspace === "runtimes" ? <Runtimes dashboard={dashboard} openOperation={openOperation} />
          : workspace === "plugins" ? <Plugins operations={dashboard.operations} api={api} reload={reload} layout={pluginLayout === "inline" ? "sidebar" : pluginLayout} setLayout={setPluginLayout} />
            : workspace === "lyf" ? <Suspense fallback={<div className="min-h-[382px]" />}><LyfResourceView page={lyfResources} /></Suspense>
            : workspace === "developer" ? <Suspense fallback={<div className="min-h-[382px]" />}><DeveloperView layout={pluginLayout} changeLayout={setPluginLayout} duration={toastDuration} changeDuration={setToastDuration} /></Suspense>
            : <Configuration dashboard={dashboard} />;

  return <>{content}{operation ? <Suspense fallback={null}><OperationDialog operation={operation} close={closeOperation} api={api} reload={reload} /></Suspense> : null}</>;
});

const Overview = memo(function Overview({ dashboard }: { dashboard: Dashboard }) {
  const { t } = useLocale();
  const running = dashboard.runtimes.filter((runtime) => runtime.state === "ready").length;
  const unresolved = dashboard.audit.filter((record) => ["failed", "unknown"].includes(record.state)).length;
  return <div className="webui-overview-layout">
    <section className="webui-overview-metrics webui-overview-wide"><Metric label={t("webui.metric.active_runtimes")} value={String(running)} detail={t("webui.metric.configured", { count: dashboard.runtimes.length })} /><Metric label={t("webui.metric.enabled_plugins")} value={String(dashboard.plugins.length)} detail={t("webui.metric.loaded_generations")} /><Metric label={t("webui.metric.operation_records")} value={String(dashboard.ledger.length)} detail={t("webui.metric.retained_evidence")} /><Metric label={t("webui.metric.unresolved_faults")} value={String(unresolved)} detail={unresolved === 0 ? t("webui.metric.none_recorded") : t("webui.metric.requires_review")} emphasis={unresolved > 0} /></section>
    <Ledger dashboard={dashboard} compact />
    <aside className="webui-overview-aside"><RuntimeHealth dashboard={dashboard} /><RecentEvidence dashboard={dashboard} /></aside>
  </div>;
});

const Metric = memo(function Metric({ label, value, detail, emphasis = false }: { label: string; value: string; detail: string; emphasis?: boolean }) {
  return <SurfaceCard><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><strong className={cn("mt-2 block font-mono text-[26px] font-semibold", emphasis && "text-amber-600")}>{value}</strong><span className="mt-1 block text-[11px] text-muted-foreground">{detail}</span></CardContent></SurfaceCard>;
});

const Ledger = memo(function Ledger({ dashboard, compact = false }: { dashboard: Dashboard; compact?: boolean }) {
  const { t } = useLocale();
  return <SurfaceCard className={cn("webui-overview-ledger", compact && "webui-overview-ledger--compact")}><CardHeader className="flex-row items-start justify-between px-5 pt-5"><CardTitle className="text-sm font-semibold">{t("webui.ledger.title")}</CardTitle></CardHeader><CardContent className="px-5 pb-5">{dashboard.ledger.length === 0 ? <Empty label={t("webui.ledger.empty")} /> : <VirtualLedgerTable items={dashboard.ledger} />}</CardContent></SurfaceCard>;
});

const VirtualLedgerTable = memo(function VirtualLedgerTable({ items }: { items: LedgerView[] }) {
  const { t } = useLocale();
  const scrollRef = useRef<HTMLDivElement>(null);
  const getItemKey = useCallback((index: number) => items[index].id, [items]);
  const virtualizer = useVirtualizer({ count: items.length, getScrollElement: () => scrollRef.current, estimateSize: () => 58, getItemKey, overscan: 6 });
  const virtualItems = virtualizer.getVirtualItems();
  const paddingTop = virtualItems[0]?.start ?? 0;
  const paddingBottom = virtualizer.getTotalSize() - (virtualItems.at(-1)?.end ?? 0);

  return <div ref={scrollRef} data-slot="ledger-viewport" className="max-h-[310px] overflow-auto"><Table className="table-fixed"><colgroup><col /><col className="w-28" /><col className="hidden w-40 sm:table-column" /></colgroup><TableHeader className="sticky top-0 z-10 bg-card"><TableRow><TableHead>{t("webui.ledger.operation")}</TableHead><TableHead>{t("webui.ledger.state")}</TableHead><TableHead className="hidden sm:table-cell">{t("webui.ledger.updated")}</TableHead></TableRow></TableHeader><TableBody>{paddingTop > 0 ? <tr aria-hidden="true"><td colSpan={3} className="h-0 p-0" style={{ height: paddingTop }} /></tr> : null}{virtualItems.map((virtualItem) => <LedgerRow key={virtualItem.key} item={items[virtualItem.index]} height={virtualItem.size} index={virtualItem.index} />)}{paddingBottom > 0 ? <tr aria-hidden="true"><td colSpan={3} className="h-0 p-0" style={{ height: paddingBottom }} /></tr> : null}</TableBody></Table></div>;
});

const LedgerRow = memo(function LedgerRow({ item, height, index }: { item: LedgerView; height: number; index: number }) {
  return <TableRow data-virtual-index={index} style={{ height }}><TableCell><div><p className="font-medium">{item.title}</p><p className="font-mono text-xs text-muted-foreground">{item.source}</p></div></TableCell><TableCell><State value={item.status} /></TableCell><TableCell className="hidden font-mono text-xs text-muted-foreground sm:table-cell">{item.at}</TableCell></TableRow>;
});

const RuntimeHealth = memo(function RuntimeHealth({ dashboard }: { dashboard: Dashboard }) {
  const { t } = useLocale();
  return <SurfaceCard className="webui-overview-side-card"><CardHeader className="px-4 pt-4"><CardTitle className="text-sm font-semibold">{t("webui.runtime.health")}</CardTitle></CardHeader><CardContent className="px-4 pb-3">{dashboard.runtimes.length === 0 ? <Empty label={t("webui.runtime.empty")} /> : <div className="grid">{dashboard.runtimes.slice(0, 4).map((runtime) => <div className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-2 border-t py-3 first:border-t-0" key={runtime.id}><span className="webui-runtime-mark"><Cable size={15} /></span><div className="min-w-0"><p className="truncate text-xs font-semibold">{runtime.id}</p><p className="mt-0.5 truncate text-[11px] text-muted-foreground">{runtime.kind} · {runtime.activity}</p></div><State value={runtime.state} /></div>)}</div>}</CardContent></SurfaceCard>;
});

const RecentEvidence = memo(function RecentEvidence({ dashboard }: { dashboard: Dashboard }) {
  const { t } = useLocale();
  const evidence = dashboard.audit.slice(0, 3);
  return <SurfaceCard className="webui-overview-side-card"><CardHeader className="px-4 pt-4"><CardTitle className="text-sm font-semibold">{t("webui.audit.recent")}</CardTitle></CardHeader><CardContent className="px-4 pb-3">{evidence.length === 0 ? <Empty label={t("webui.audit.empty")} /> : evidence.map((record) => <div className="grid grid-cols-[18px_minmax(0,1fr)_16px] items-center gap-2 border-t py-3" key={record.id}><CircleDot className="text-amber-500" size={16} /><div className="min-w-0"><p className="truncate text-xs font-semibold">{record.operation}</p><p className="mt-0.5 truncate text-[11px] text-muted-foreground">{record.target} · {record.updated_at}</p></div><ArrowRight className="text-muted-foreground" size={15} /></div>)}</CardContent></SurfaceCard>;
});

const Runtimes = memo(function Runtimes({ dashboard, openOperation }: { dashboard: Dashboard; openOperation: (operation: WebUiOperation) => void }) {
  const { t } = useLocale();
  return <SurfaceCard><CardHeader className="flex-row items-start justify-between"><CardTitle>{t("webui.runtimes.title")}</CardTitle>{dashboard.operations[0] ? <Button size="sm" onClick={() => openOperation(dashboard.operations[0])}>{t("webui.runtimes.queue_action")}</Button> : null}</CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>{t("webui.runtimes.runtime")}</TableHead><TableHead>{t("webui.ledger.state")}</TableHead><TableHead className="hidden md:table-cell">{t("webui.runtimes.protocol")}</TableHead><TableHead className="hidden md:table-cell">{t("webui.runtimes.activity")}</TableHead></TableRow></TableHeader><TableBody>{dashboard.runtimes.map((runtime) => <TableRow key={runtime.id}><TableCell><p className="font-medium">{runtime.id}</p><p className="text-xs text-muted-foreground">{runtime.kind}</p></TableCell><TableCell><State value={runtime.state} /></TableCell><TableCell className="hidden font-mono text-xs md:table-cell">{runtime.protocol}</TableCell><TableCell className="hidden text-xs text-muted-foreground md:table-cell">{runtime.activity}</TableCell></TableRow>)}</TableBody></Table></CardContent></SurfaceCard>;
});

const Plugins = memo(function Plugins({ operations, api, reload, layout, setLayout }: { operations: WebUiOperation[]; api: WebUiApi; reload: () => Promise<void>; layout: WebUiLayout; setLayout: (layout: WebUiLayout) => void }) {
  return <PluginWorkspace operations={operations} api={api} reload={reload} layout={layout} setLayout={setLayout} />;
});

function EventSummary({ api }: { api: WebUiApi }) {
  const { t } = useLocale();
  const [summary, setSummary] = useState<import("@/models/api").EventSummary | null>(null);
  useEffect(() => { void api.eventSummary().then(setSummary); }, [api]);
  return <SurfaceCard><CardHeader><CardTitle>{t("webui.events.summary")}</CardTitle></CardHeader><CardContent className="grid gap-3 sm:grid-cols-4">{Object.entries(summary?.totals ?? {}).map(([key, value]) => <div className="ly-card-metric" key={key}><span>{key}</span><strong>{value}</strong></div>)}</CardContent></SurfaceCard>;
}

const Topology = memo(function Topology({ dashboard }: { dashboard: Dashboard }) {
  const { t } = useLocale();
  return <div className="grid gap-4 md:grid-cols-2"><TopologyCard icon={ShieldCheck} title={t("webui.topology.kernel")} rows={[[dashboard.version, dashboard.kernelState]]} /><TopologyCard icon={Cable} title={t("webui.topology.runtimes")} rows={dashboard.runtimes.map((runtime) => [runtime.id, runtime.state])} /><TopologyCard icon={Boxes} title={t("webui.topology.plugins")} rows={dashboard.plugins.map((plugin) => [plugin.id, plugin.state])} /><TopologyCard icon={FileClock} title={t("webui.topology.audit")} rows={[[t("webui.topology.records", { count: dashboard.audit.length }), "retained"]]} /></div>;
});

function TopologyCard({ icon: Icon, title, rows }: { icon: typeof ShieldCheck; title: string; rows: string[][] }) {
  return <SurfaceCard><CardHeader><CardTitle className="flex items-center gap-2 text-sm"><Icon size={16} className="text-primary" />{title}</CardTitle></CardHeader><CardContent className="grid gap-2">{rows.map(([label, state]) => <div key={label} className="flex items-center justify-between rounded-md bg-muted/45 px-3 py-2 text-sm"><span className="font-mono text-xs">{label}</span><State value={state} /></div>)}</CardContent></SurfaceCard>;
}

const Configuration = memo(function Configuration({ dashboard }: { dashboard: Dashboard }) {
  const { t } = useLocale();
  return <SurfaceCard><CardHeader><CardTitle>{t("webui.about.title")}</CardTitle></CardHeader><CardContent className="grid divide-y"><Setting label={t("webui.about.instance")} value={dashboard.instance} /><Setting label={t("webui.about.kernel")} value={dashboard.version} /><Setting label={t("webui.about.transport")} value={t("webui.configuration.loopback")} /><Setting label={t("webui.about.owner")} value={t("webui.configuration.daemon")} /></CardContent></SurfaceCard>;
});

function Setting({ label, value }: { label: string; value: string }) {
  return <div className="grid gap-1 py-4 sm:grid-cols-[180px_1fr]"><span className="text-sm text-muted-foreground">{label}</span><strong className="font-mono text-sm">{value}</strong></div>;
}

const State = memo(function State({ value }: { value: string }) {
  const { t } = useLocale();
  const positive = POSITIVE_STATES.has(value);
  const warning = WARNING_STATES.has(value);
  return <Badge variant={positive ? "secondary" : warning ? "outline" : "destructive"} className={cn("capitalize", positive && "border-emerald-200 bg-emerald-50 text-emerald-700")}>{t(`webui.state.${value}`)}</Badge>;
});

function Empty({ label }: { label: string }) {
  return <div className="grid min-h-32 place-items-center border-t text-sm text-muted-foreground">{label}</div>;
}
