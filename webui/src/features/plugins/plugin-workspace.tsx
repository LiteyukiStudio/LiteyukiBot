import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Boxes, CircleAlert, RefreshCw, Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLocale } from "@/i18n/locale";
import type { PluginDiscoveryPage, PluginDiscoveryRecord, PluginPreview, PluginTargetPage, WebUiLayout, WebUiOperation } from "@/models/api";
import { WebUiApi } from "@/services/webui-api";
import { PluginDiscoverView, INITIAL_PLUGIN_SEARCH_FILTERS, type PluginSearchFilters } from "@/features/plugins/plugin-discover-view";
import { PluginManagedView } from "@/features/plugins/plugin-managed-view";
import { PluginHostedView } from "@/features/plugins/plugin-hosted-view";
import { PluginIndexView } from "@/features/plugins/plugin-index-view";
import { PluginPreviewDialog } from "@/features/plugins/plugin-preview-dialog";
import { PluginDetailsView } from "@/features/plugins/plugin-details-view";
import { cn } from "@/lib/utils";

const OperationDialog = lazy(() => import("@/features/operations/operation-dialog").then(({ OperationDialog: Dialog }) => ({ default: Dialog })));

type PluginWorkspaceProps = {
  operations: WebUiOperation[];
  api: WebUiApi;
  reload: () => Promise<void>;
  layout: WebUiLayout;
  setLayout: (layout: WebUiLayout) => void;
};

export function PluginWorkspace({ operations, api, reload, layout, setLayout }: PluginWorkspaceProps) {
  const { t } = useLocale();
  const [tab, setTab] = useState("discover");
  const [followed, setFollowed] = useState<string[]>([]);
  const [sourceOrder, setSourceOrder] = useState<string[]>([]);
  const [disabledSources, setDisabledSources] = useState<string[]>([]);
  const [filters, setFilters] = useState<PluginSearchFilters>(INITIAL_PLUGIN_SEARCH_FILTERS);
  const [discovery, setDiscovery] = useState<PluginDiscoveryPage | null>(null);
  const [targets, setTargets] = useState<PluginTargetPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTargetId, setSelectedTargetId] = useState("");
  const [selectedBundleId, setSelectedBundleId] = useState("");
  const [preview, setPreview] = useState<PluginPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [operation, setOperation] = useState<WebUiOperation | null>(null);
  const [operationValues, setOperationValues] = useState<Record<string, string>>({});
  const [details, setDetails] = useState<import("@/models/api").PluginDetails | null>(null);

  const fetchData = useCallback(async (nextFilters: PluginSearchFilters, refresh = false, cursor: string | null = null, append = false): Promise<boolean> => {
    setLoading(true);
    try {
      const [nextDiscovery, nextTargets] = await Promise.all([
        api.pluginDiscovery({
          query: nextFilters.query,
          sourceId: nextFilters.sourceId,
          runtimeKind: nextFilters.runtimeKind,
          status: nextFilters.status,
          refresh,
          cursor,
        }),
        api.pluginTargets(),
      ]);
      const visibleDiscovery = { ...nextDiscovery, sources: nextDiscovery.sources.filter((source) => !disabledSources.includes(source.id)), items: nextDiscovery.items.filter((item) => !disabledSources.includes(item.source)) };
      setDiscovery((current) => append && current ? { ...visibleDiscovery, items: [...current.items, ...visibleDiscovery.items] } : visibleDiscovery);
      setTargets(nextTargets);
      setSelectedTargetId((current) => nextTargets.items.some((item) => item.id === current) ? current : nextTargets.items[0]?.id ?? "");
      setError(null);
      return true;
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "webui.plugins.load_failed";
      setError(message);
      toast.error(message);
      return false;
    } finally {
      setLoading(false);
    }
  }, [api, disabledSources]);

  useEffect(() => { void fetchData(INITIAL_PLUGIN_SEARCH_FILTERS); }, [fetchData]);
  useEffect(() => { void api.followedPlugins().then((value) => setFollowed(value.followed ?? [])).catch(() => undefined); }, [api]);
  useEffect(() => { void api.preferences().then((value) => { setSourceOrder(value.plugin_sources ?? []); setDisabledSources(value.disabled_plugin_sources ?? []); }).catch(() => undefined); }, [api]);
  useEffect(() => {
    const onTab = (event: Event) => {
      const value = (event as CustomEvent<string>).detail;
      setTab(["discover", "index", "managed", "hosted", "followed"].includes(value) ? value : "discover");
    };
    window.addEventListener("liteyuki:plugin-tab", onTab);
    return () => window.removeEventListener("liteyuki:plugin-tab", onTab);
  }, []);

  const toggleFollowed = async (bundleId: string) => {
    const next = followed.includes(bundleId) ? followed.filter((item) => item !== bundleId) : [...followed, bundleId];
    setFollowed(next);
    try { await api.updateFollowedPlugins(next); } catch { setFollowed(followed); }
  };
  const updateSources = (nextOrder: string[], nextDisabled: string[]) => {
    setSourceOrder(nextOrder); setDisabledSources(nextDisabled);
    void api.updatePreferences({ plugin_layout: layout, plugin_sources: nextOrder, disabled_plugin_sources: nextDisabled }).catch(() => undefined);
  };
  const refreshIndex = async () => {
    const toastId = toast.loading(t("webui.plugins.refreshing"));
    const success = await fetchData(filters, true);
    if (success) toast.success(t("webui.plugins.refresh_done"), { id: toastId });
    else toast.error(t("webui.plugins.refresh_failed"), { id: toastId });
  };

  const selectedTarget = targets?.items.find((item) => item.id === selectedTargetId) ?? null;
  const installOperation = operations.find((item) => item.id === "management.plugin.install");

  const selectOperation = (id: string, values: Record<string, string>) => {
    const next = operations.find((item) => item.id === id);
    if (!next) {
      toast.error(t("webui.plugins.operation_missing"));
      return;
    }
    setOperationValues(values);
    setOperation(next);
  };

  const loadPreview = async (item: PluginDiscoveryRecord) => {
    if (!selectedTarget) return;
    setPreviewLoading(true);
    try {
      setPreview(await api.pluginPreview(item.bundle_id, item.source, selectedTarget.id));
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : t("webui.plugins.preview_failed"));
    } finally {
      setPreviewLoading(false);
    }
  };
  const loadDetails = async (item: PluginDiscoveryRecord) => {
    try { setDetails(await api.pluginDetails(item.bundle_id, item.source)); } catch (cause) { toast.error(cause instanceof Error ? cause.message : t("webui.plugins.details_failed")); }
  };

  const queueInstall = async () => {
    if (!preview || !installOperation) return;
    try {
      await api.submit(installOperation, preview.selected_target.id, {
        runtime_id: preview.selected_target.id,
        bundle_id: preview.bundle.bundle_id,
        source_id: preview.source.id,
        expected_index_digest: preview.index_digest,
      }, true);
      toast.success(t("webui.plugins.install_queued"));
      setPreview(null);
      await reload();
      await fetchData(filters);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : t("webui.plugins.install_failed"));
    }
  };

  const followedDiscovery = discovery ? { ...discovery, items: discovery.items.filter((item) => followed.includes(item.bundle_id)) } : null;
  const tabContent = tab === "discover" || tab === "followed" ? <PluginDiscoverView discovery={tab === "followed" ? followedDiscovery : discovery} targets={targets} selectedTargetId={selectedTargetId} setSelectedTargetId={setSelectedTargetId} filters={filters} loading={loading} refresh={() => void refreshIndex()} search={(next) => { setFilters(next); void fetchData(next); }} loadMore={() => { if (discovery?.next_cursor) void fetchData(filters, false, discovery.next_cursor, true); }} loadPreview={loadPreview} previewLoading={previewLoading} followed={followed} toggleFollowed={toggleFollowed} openDetails={loadDetails} /> : tab === "index" ? <PluginIndexView discovery={discovery} order={sourceOrder} disabled={disabledSources} update={updateSources} /> : tab === "hosted" ? <PluginHostedView targets={targets} /> : <PluginManagedView targets={targets} selectedTargetId={selectedTargetId} setSelectedTargetId={setSelectedTargetId} selectedBundleId={selectedBundleId} setSelectedBundleId={setSelectedBundleId} loading={loading} selectOperation={selectOperation} />;
  const subnav = <nav className="webui-plugin-subnav">{(["discover", "index", "managed", "hosted", "followed"] as const).map((item) => <Button key={item} variant="ghost" className={cn("webui-sidebar-control", tab === item && "webui-developer-sidebar-select", "justify-start")} onClick={() => setTab(item)}>{t(`webui.plugins.${item}`)}</Button>)}</nav>;
  if (details) return <PluginDetailsView details={details} followed={followed.includes(details.selected.bundle_id)} toggleFollowed={() => toggleFollowed(details.selected.bundle_id)} close={() => setDetails(null)} />;
  return <div className="webui-plugin-workspace">
    <div className="webui-plugin-header"><div><h2 className="webui-plugin-title"><Boxes size={20} className="text-primary" />{t("webui.plugins.title")}</h2><p className="webui-plugin-subtitle">{t("webui.plugins.subtitle")}</p></div><Button variant="outline" size="icon" aria-label={t("webui.plugins.refresh")} onClick={() => void fetchData(filters, true)} disabled={loading}><RefreshCw className={loading ? "animate-spin" : undefined} size={16} /></Button></div>
    {error ? <div className="webui-plugin-error"><CircleAlert size={17} /><span>{error}</span></div> : null}
    {layout === "sidebar" ? <div className="webui-plugin-sidebar-layout">{subnav}<div>{tabContent}</div></div> : layout === "main-sidebar" ? tabContent : <Tabs value={tab} onValueChange={setTab} className="webui-plugin-tabs flex-col gap-4">
      <TabsList className="webui-plugin-tabs-list" aria-label={t("webui.plugins.views")}><TabsTrigger value="discover">{t("webui.plugins.discover")}</TabsTrigger><TabsTrigger value="index">{t("webui.plugins.index")}</TabsTrigger><TabsTrigger value="managed">{t("webui.plugins.managed")}</TabsTrigger><TabsTrigger value="hosted">{t("webui.plugins.hosted")}</TabsTrigger><TabsTrigger value="followed">{t("webui.plugins.followed")}</TabsTrigger></TabsList>
      <TabsContent value={tab}>{tabContent}</TabsContent>
    </Tabs>}
    <PluginPreviewDialog preview={preview} installOperation={installOperation} close={() => setPreview(null)} install={() => void queueInstall()} />
    {operation ? <Suspense fallback={null}><OperationDialog operation={operation} close={() => setOperation(null)} api={api} reload={reload} initialValues={operationValues} /></Suspense> : null}
  </div>;
}
