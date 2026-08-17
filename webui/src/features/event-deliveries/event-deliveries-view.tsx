import { useCallback, useEffect, useState, type FormEvent } from "react";
import { CircleAlert, Filter, LoaderCircle, RefreshCw, Route, Server, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SurfaceCard } from "@/components/surface-card";
import { useLocale } from "@/i18n/locale";
import type {
  EventDeliveryDetail,
  EventDeliveryFilters,
  EventDeliveryPage,
  EventDeliveryRecord,
} from "@/models/api";
import type { WebUiApi } from "@/services/webui-api";

type EventDeliveriesViewProps = {
  initial: EventDeliveryPage;
  api: WebUiApi;
  reloadInitial: () => Promise<void>;
};

const stateOptions = ["", "active", "settled", "pending", "offered", "accepted", "completed", "failed", "expired"];

export function EventDeliveriesView({ initial, api, reloadInitial }: EventDeliveriesViewProps) {
  const { t } = useLocale();
  const [page, setPage] = useState(initial);
  const [filters, setFilters] = useState<EventDeliveryFilters>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<EventDeliveryDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => setPage(initial), [initial]);

  const load = useCallback(async (nextFilters: EventDeliveryFilters, cursor: string | null = null) => {
    setLoading(true);
    setError(null);
    try {
      setPage(await api.eventDeliveries(nextFilters, cursor));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "webui.event_deliveries_unavailable");
    } finally {
      setLoading(false);
    }
  }, [api]);

  const selectRecord = useCallback(async (record: EventDeliveryRecord) => {
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      setDetail(await api.eventDelivery(record.id));
    } catch (cause) {
      setDetailError(cause instanceof Error ? cause.message : "webui.event_delivery_unavailable");
    } finally {
      setDetailLoading(false);
    }
  }, [api]);

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void load(filters);
  };
  const clearFilters = () => {
    setFilters({});
    void load({});
  };
  const refresh = () => {
    void reloadInitial();
  };

  return <div className="grid gap-4">
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Metric label={t("webui.event_delivery.active")} value={`${page.broker.active} / ${page.broker.active_capacity}`} />
      <Metric label={t("webui.event_delivery.terminal")} value={`${page.broker.terminal} / ${page.broker.terminal_capacity}`} />
      <Metric label={t("webui.event_delivery.broker_state")} value={page.broker.state} />
      <Metric label={t("webui.event_delivery.bridges")} value={String(page.broker.bridges.length)} />
    </section>
    <SurfaceCard>
      <CardHeader className="flex-row items-center justify-between gap-4 px-5 pt-5">
        <div className="min-w-0"><CardTitle className="text-sm font-semibold">{t("webui.event_delivery.title")}</CardTitle><p className="mt-1 text-xs text-muted-foreground">{t("webui.event_delivery.retention")}</p></div>
        <Button variant="outline" size="icon" onClick={refresh} aria-label={t("webui.action.refresh")}><RefreshCw size={15} /></Button>
      </CardHeader>
      <CardContent className="space-y-4 px-5 pb-5">
        <form className="grid gap-2 md:grid-cols-6" onSubmit={applyFilters}>
          <label className="grid gap-1 text-xs text-muted-foreground"><span>{t("webui.event_delivery.filter.state")}</span><select value={filters.state ?? ""} onChange={(event) => setFilters((current) => ({ ...current, state: event.target.value || undefined }))} className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm text-foreground"><option value="">{t("webui.event_delivery.filter.any")}</option>{stateOptions.slice(1).map((state) => <option key={state} value={state}>{state}</option>)}</select></label>
          <FilterInput label={t("webui.event_delivery.filter.topic")} value={filters.topic ?? ""} onChange={(value) => setFilters((current) => ({ ...current, topic: value || undefined }))} />
          <FilterInput label={t("webui.event_delivery.filter.source")} value={filters.source ?? ""} onChange={(value) => setFilters((current) => ({ ...current, source: value || undefined }))} />
          <FilterInput label={t("webui.event_delivery.filter.target")} value={filters.target ?? ""} onChange={(value) => setFilters((current) => ({ ...current, target: value || undefined }))} />
          <FilterInput label={t("webui.event_delivery.filter.failure")} value={filters.failure ?? ""} onChange={(value) => setFilters((current) => ({ ...current, failure: value || undefined }))} />
          <div className="flex items-end gap-2"><Button type="submit" className="flex-1" size="sm" disabled={loading}><Filter size={14} />{t("webui.event_delivery.filter.apply")}</Button><Button type="button" variant="outline" size="icon" onClick={clearFilters} aria-label={t("webui.event_delivery.filter.clear")}><X size={15} /></Button></div>
        </form>
        {error ? <div className="webui-event-delivery-error"><CircleAlert size={16} /><span>{t("webui.event_delivery.error")}</span><code>{error}</code><Button size="sm" variant="outline" onClick={() => void load(filters)}>{t("webui.action.retry")}</Button></div> : null}
        <div className="flex flex-wrap gap-2 border-y py-3 text-xs text-muted-foreground">{page.broker.bridges.length === 0 ? <span>{t("webui.event_delivery.bridges_empty")}</span> : page.broker.bridges.map((bridge) => <span className="webui-event-delivery-bridge" key={bridge.id}><Server size={13} /><span className="font-mono">{bridge.id}</span><Status value={bridge.session_state ?? bridge.state} /></span>)}</div>
        <div className="overflow-x-auto"><Table className="min-w-[760px]"><TableHeader><TableRow><TableHead>{t("webui.event_delivery.table.topic")}</TableHead><TableHead>{t("webui.event_delivery.table.source")}</TableHead><TableHead>{t("webui.event_delivery.table.status")}</TableHead><TableHead>{t("webui.event_delivery.table.targets")}</TableHead><TableHead>{t("webui.event_delivery.table.observed")}</TableHead></TableRow></TableHeader><TableBody>{loading ? <TableRow><TableCell colSpan={5}><span className="flex items-center justify-center gap-2 py-8 text-muted-foreground"><LoaderCircle className="animate-spin" size={16} />{t("webui.event_delivery.loading")}</span></TableCell></TableRow> : page.items.length === 0 ? <TableRow><TableCell colSpan={5}><p className="py-8 text-center text-sm text-muted-foreground">{t("webui.event_delivery.empty")}</p></TableCell></TableRow> : page.items.map((record) => <TableRow key={record.id} className="cursor-pointer" onClick={() => void selectRecord(record)}><TableCell><p className="font-mono text-xs font-medium">{record.topic}</p><p className="mt-1 font-mono text-[11px] text-muted-foreground">{record.id}</p></TableCell><TableCell className="font-mono text-xs">{record.source}</TableCell><TableCell><Status value={record.status} code={record.failure_code} /></TableCell><TableCell className="font-mono text-xs">{record.failed_count ? `${record.failed_count} / ${record.target_count ?? 0}` : record.target_count ?? "-"}</TableCell><TableCell className="font-mono text-xs text-muted-foreground">{record.observed_at ?? "-"}</TableCell></TableRow>)}</TableBody></Table></div>
        {page.next_cursor ? <div className="flex justify-end"><Button variant="outline" size="sm" onClick={() => void load(filters, page.next_cursor)}>{t("webui.event_delivery.next_page")}</Button></div> : null}
      </CardContent>
    </SurfaceCard>
    <EventDeliveryDrawer detail={detail} error={detailError} loading={detailLoading} onOpenChange={(open) => { if (!open) { setDetail(null); setDetailError(null); } }} />
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <SurfaceCard><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><strong className="mt-2 block font-mono text-[22px] font-semibold">{value}</strong></CardContent></SurfaceCard>;
}

function FilterInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="grid gap-1 text-xs text-muted-foreground"><span>{label}</span><Input value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function Status({ value, code }: { value: string; code?: string }) {
  const warning = ["failed", "expired", "disconnected", "unavailable"].includes(value);
  return <Badge variant={warning ? "destructive" : "secondary"} className="gap-1 font-mono text-[10px]">{value}{code ? `: ${code}` : ""}</Badge>;
}

function EventDeliveryDrawer({ detail, error, loading, onOpenChange }: { detail: EventDeliveryDetail | null; error: string | null; loading: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useLocale();
  const open = detail !== null || error !== null || loading;
  return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-xl"><SheetHeader><SheetTitle>{t("webui.event_delivery.detail.title")}</SheetTitle><SheetDescription>{detail?.id ?? t("webui.event_delivery.detail.redacted")}</SheetDescription></SheetHeader>{loading ? <div className="grid flex-1 place-items-center"><LoaderCircle className="animate-spin text-muted-foreground" /></div> : error ? <div className="m-4 webui-event-delivery-error"><CircleAlert size={16} /><span>{t("webui.event_delivery.detail.error")}</span><code>{error}</code></div> : detail ? <div className="grid gap-5 px-4 pb-5"><section className="grid gap-2 text-sm"><DetailRow label={t("webui.event_delivery.table.topic")} value={detail.topic} /><DetailRow label={t("webui.event_delivery.table.source")} value={detail.source} /><DetailRow label={t("webui.event_delivery.table.status")} value={detail.status} /><DetailRow label={t("webui.event_delivery.table.observed")} value={detail.observed_at ?? "-"} /></section><section><h2 className="mb-2 text-sm font-semibold">{t("webui.event_delivery.detail.deliveries")}</h2><div className="grid gap-2">{detail.deliveries.length === 0 ? <p className="text-sm text-muted-foreground">{t("webui.event_delivery.detail.deliveries_empty")}</p> : detail.deliveries.map((delivery, index) => <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 rounded-md border p-3" key={delivery.id ?? `${delivery.target}-${index}`}><div className="min-w-0"><p className="truncate font-mono text-xs">{delivery.target}</p><p className="mt-1 font-mono text-[11px] text-muted-foreground">{delivery.updated_at ?? "-"}</p></div><Status value={delivery.state} code={delivery.failure_code} /></div>)}</div></section><section><h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Route size={15} />{t("webui.event_delivery.detail.timeline")}</h2><ol className="grid gap-3 border-l pl-4">{detail.timeline.length === 0 ? <li className="text-sm text-muted-foreground">{t("webui.event_delivery.detail.timeline_empty")}</li> : detail.timeline.map((transition, index) => <li className="relative" key={`${transition.at}-${transition.phase}-${index}`}><span className="absolute -left-[21px] top-1.5 size-2 rounded-full bg-primary" /><p className="font-mono text-xs">{transition.phase} · {transition.state}</p><p className="mt-1 text-xs text-muted-foreground">{transition.at}{transition.target ? ` · ${transition.target}` : ""}{transition.code ? ` · ${transition.code}` : ""}</p></li>)}</ol></section></div> : null}</SheetContent></Sheet>;
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return <div className="grid grid-cols-[112px_minmax(0,1fr)] gap-3"><span className="text-muted-foreground">{label}</span><span className="truncate font-mono text-xs">{value}</span></div>;
}
