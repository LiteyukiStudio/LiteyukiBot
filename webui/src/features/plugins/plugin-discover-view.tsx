import { useEffect, useState, type FormEvent } from "react";
import { CircleAlert, LoaderCircle, RefreshCw, Search, ShieldCheck, Star } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PluginTargetSelect, formatPluginBytes } from "@/components/plugin-ui";
import { useLocale } from "@/i18n/locale";
import type { PluginDiscoveryPage, PluginDiscoveryRecord, PluginTargetPage } from "@/models/api";
import { cn } from "@/lib/utils";

export type PluginSearchFilters = {
  query: string;
  sourceId?: string;
  runtimeKind?: string;
  status: "active" | "yanked" | "all";
};

export const INITIAL_PLUGIN_SEARCH_FILTERS: PluginSearchFilters = { query: "", status: "active" };

export type PluginDiscoverViewProps = {
  discovery: PluginDiscoveryPage | null;
  targets: PluginTargetPage | null;
  selectedTargetId: string;
  setSelectedTargetId: (id: string) => void;
  filters: PluginSearchFilters;
  loading: boolean;
  refresh: () => void;
  search: (filters: PluginSearchFilters) => void;
  loadMore: () => void;
  loadPreview: (item: PluginDiscoveryRecord) => Promise<void>;
  previewLoading: boolean;
  followed: string[];
  toggleFollowed: (bundleId: string) => Promise<void>;
  openDetails: (item: PluginDiscoveryRecord) => Promise<void>;
};

export function PluginDiscoverView({
  discovery,
  targets,
  selectedTargetId,
  setSelectedTargetId,
  filters,
  loading,
  refresh,
  search,
  loadMore,
  loadPreview,
  previewLoading,
  followed,
  toggleFollowed,
  openDetails,
}: PluginDiscoverViewProps) {
  const { t } = useLocale();
  const [draft, setDraft] = useState(filters);

  useEffect(() => setDraft(filters), [filters]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    search(draft);
  };
  const targetItems = targets?.items ?? [];
  const runtimeKinds = Array.from(new Set(targetItems.map((target) => target.kind)));
  return <div className="webui-plugin-view">
    <Card>
      <CardHeader className="webui-plugin-panel-header"><div><CardTitle className="text-base">{t("webui.plugins.discover")}</CardTitle><CardDescription>{t("webui.plugins.discover_description")}</CardDescription></div></CardHeader>
      <CardContent className="webui-plugin-filter-content">
        <form className="webui-plugin-filter-grid" onSubmit={submit}>
          <label className="sr-only" htmlFor="plugin-search">{t("webui.plugins.search")}</label>
          <Input id="plugin-search" value={draft.query} onChange={(event) => setDraft({ ...draft, query: event.target.value })} placeholder={t("webui.plugins.search_placeholder")} />
          <select aria-label={t("webui.plugins.source")} className="webui-plugin-select" value={draft.sourceId ?? ""} onChange={(event) => setDraft({ ...draft, sourceId: event.target.value || undefined })}><option value="">{t("webui.plugins.all_sources")}</option>{discovery?.sources.map((source) => <option value={source.id} key={source.id}>{source.id}</option>)}</select>
          <select aria-label={t("webui.plugins.runtime")} className="webui-plugin-select" value={draft.runtimeKind ?? ""} onChange={(event) => setDraft({ ...draft, runtimeKind: event.target.value || undefined })}><option value="">{t("webui.plugins.all_runtimes")}</option>{runtimeKinds.map((kind) => <option value={kind} key={kind}>{kind}</option>)}</select>
          <select aria-label={t("webui.plugins.status")} className="webui-plugin-select" value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as PluginSearchFilters["status"] })}><option value="active">{t("webui.plugins.active")}</option><option value="all">{t("webui.plugins.all_statuses")}</option><option value="yanked">{t("webui.plugins.yanked")}</option></select>
          <PluginTargetSelect targets={targetItems} value={selectedTargetId} onChange={setSelectedTargetId} label={t("webui.plugins.target")} emptyLabel={t("webui.plugins.select_target")} />
          <Button type="submit" disabled={loading}><Search size={15} />{t("webui.plugins.search")}</Button>
        </form>
        <div className="webui-plugin-source-row"><span>{t("webui.plugins.sources")}</span>{discovery?.sources.map((source) => <Badge key={source.id} variant="outline" className="gap-1 font-mono text-[10px]"><span className={cn("size-1.5 rounded-full", source.cache_state === "cached" ? "bg-emerald-500" : "bg-amber-500")} />{source.id}</Badge>)}<Button className="webui-plugin-refresh" variant="ghost" size="sm" onClick={refresh} disabled={loading}><RefreshCw size={13} />{t("webui.plugins.refresh")}</Button></div>
      </CardContent>
    </Card>
    <div className="webui-plugin-result-list">
      {discovery?.items.map((item) => <DiscoveryRow key={`${item.source}:${item.bundle_id}`} item={item} disabled={!selectedTargetId || previewLoading} onPreview={() => void loadPreview(item)} openDetails={() => void openDetails(item)} followed={followed.includes(item.bundle_id)} toggleFollowed={toggleFollowed} />)}
      {loading ? <div className="webui-plugin-loading"><LoaderCircle className="animate-spin" size={18} /></div> : discovery && discovery.items.length === 0 ? <div className="webui-plugin-empty">{t("webui.plugins.no_results")}</div> : null}
    </div>
    {discovery?.next_cursor ? <Button className="webui-plugin-load-more" variant="outline" onClick={loadMore} disabled={loading}><RefreshCw size={14} />{t("webui.plugins.load_more")}</Button> : null}
  </div>;
}

function DiscoveryRow({ item, disabled, onPreview, openDetails, followed, toggleFollowed }: { item: PluginDiscoveryRecord; disabled: boolean; onPreview: () => void; openDetails: () => void; followed: boolean; toggleFollowed: (bundleId: string) => Promise<void> }) {
  const { t } = useLocale();
  return <div className="webui-plugin-result cursor-pointer" role="button" tabIndex={0} onClick={openDetails} onKeyDown={(event) => { if (event.key === "Enter") openDetails(); }}>
    <div className="webui-plugin-result-main">
      <div className="webui-plugin-result-heading"><div className="webui-plugin-result-title"><h3>{item.display_name}</h3><p className="webui-plugin-muted">{item.bundle_id} · {item.version}</p></div><Badge variant={item.status === "active" ? "secondary" : "outline"}>{item.status === "active" ? t("webui.plugins.active") : t("webui.plugins.yanked")}</Badge><Badge variant="outline" className="font-mono text-[10px]">{item.source}</Badge></div>
      <p className="webui-plugin-summary">{item.summary || t("webui.plugins.no_summary")}</p>
      <div className="webui-plugin-result-meta"><span>{item.publisher?.name ?? t("webui.plugins.unknown_publisher")}</span><span>{item.license?.expression ?? t("webui.plugins.unknown_license")}</span><span>{item.runtime_kinds.join(", ")}</span><span>{formatPluginBytes(item.download_bytes, item.download_bytes_exact, t("webui.plugins.size_unavailable"))}</span></div>
      <div className="webui-plugin-badge-row">{item.requested_capabilities.slice(0, 6).map((capability) => <Badge key={capability} variant="secondary" className="font-mono text-[10px]">{capability}</Badge>)}</div>
      {item.status === "yanked" && item.yanked_reason ? <p className="webui-plugin-yanked"><CircleAlert size={13} />{item.yanked_reason}</p> : null}
    </div>
    <div className="webui-plugin-result-action"><Button size="icon" variant="outline" aria-label={t("webui.plugins.followed")} onClick={(event) => { event.stopPropagation(); void toggleFollowed(item.bundle_id); }}><Star size={15} fill={followed ? "currentColor" : "none"} /></Button><Button size="sm" variant="outline" onClick={(event) => { event.stopPropagation(); onPreview(); }} disabled={disabled}><ShieldCheck size={15} />{t("webui.plugins.review_install")}</Button></div>
  </div>;
}
