import { useEffect } from "react";
import { Boxes, Check, History, RefreshCw, RotateCcw, Trash2, Undo2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PluginActionButton, PluginGenerationPanel, PluginStatePill, PluginTargetSelect } from "@/components/plugin-ui";
import { useLocale } from "@/i18n/locale";
import type { PluginTargetPage } from "@/models/api";

export type PluginManagedViewProps = {
  targets: PluginTargetPage | null;
  selectedTargetId: string;
  setSelectedTargetId: (id: string) => void;
  selectedBundleId: string;
  setSelectedBundleId: (id: string) => void;
  loading: boolean;
  selectOperation: (id: string, values: Record<string, string>) => void;
};

export function PluginManagedView({
  targets,
  selectedTargetId,
  setSelectedTargetId,
  selectedBundleId,
  setSelectedBundleId,
  loading,
  selectOperation,
}: PluginManagedViewProps) {
  const { t } = useLocale();
  const target = targets?.items.find((item) => item.id === selectedTargetId) ?? targets?.items[0] ?? null;
  const roots = target?.active_generation?.roots ?? [];
  const bundle = selectedBundleId || roots[0] || "";
  const values = target ? { runtime_id: target.id, ...(bundle ? { bundle_id: bundle } : {}) } : {};

  useEffect(() => {
    if (bundle && bundle !== selectedBundleId) setSelectedBundleId(bundle);
  }, [bundle, selectedBundleId, setSelectedBundleId]);

  if (loading && !target) return <Card><CardContent className="webui-plugin-loading"><RefreshCw className="animate-spin text-muted-foreground" /></CardContent></Card>;
  if (!target) return <Card><CardContent className="webui-plugin-empty"><Boxes size={18} />{t("webui.plugins.no_targets")}</CardContent></Card>;
  return <div className="webui-plugin-view">
    <Card>
      <CardHeader className="webui-plugin-panel-header"><div><CardTitle className="text-base">{t("webui.plugins.managed")}</CardTitle><CardDescription>{t("webui.plugins.managed_description")}</CardDescription></div><PluginTargetSelect targets={targets?.items ?? []} value={target.id} onChange={setSelectedTargetId} label={t("webui.plugins.target")} emptyLabel={t("webui.plugins.select_target")} /></CardHeader>
      <CardContent className="webui-plugin-managed-content"><div className="webui-plugin-target-status"><Badge variant="outline" className="font-mono">{target.kind}</Badge><PluginStatePill value={target.state} /><Badge variant={target.support_grade === "stable" ? "secondary" : "outline"}>{t(`webui.plugins.grade.${target.support_grade}`)}</Badge>{target.restart_required ? <Badge variant="outline" className="webui-plugin-restart"><RotateCcw size={13} />{t("webui.plugins.restart_required")}</Badge> : null}</div><div className="webui-plugin-generation-grid"><PluginGenerationPanel title={t("webui.plugins.active_generation")} generation={target.active_generation} /><PluginGenerationPanel title={t("webui.plugins.previous_generation")} generation={target.previous_generation} /></div></CardContent>
    </Card>
    <Card>
      <CardHeader className="webui-plugin-panel-header"><div><CardTitle className="text-base">{t("webui.plugins.lifecycle")}</CardTitle><CardDescription>{t("webui.plugins.lifecycle_description")}</CardDescription></div><select aria-label={t("webui.plugins.bundle")} className="webui-plugin-select webui-plugin-bundle-select" value={bundle} onChange={(event) => setSelectedBundleId(event.target.value)}><option value="">{t("webui.plugins.no_bundle")}</option>{roots.map((item) => <option value={item} key={item}>{item}</option>)}</select></CardHeader>
      <CardContent className="webui-plugin-action-row"><PluginActionButton icon={RefreshCw} label={t("webui.plugins.update")} onClick={() => selectOperation("management.plugin.update", { runtime_id: target.id })} /><PluginActionButton icon={Check} label={t("webui.plugins.enable")} disabled={!bundle} onClick={() => selectOperation("management.plugin.enable", values)} /><PluginActionButton icon={XCircle} label={t("webui.plugins.disable")} disabled={!bundle} onClick={() => selectOperation("management.plugin.disable", values)} /><PluginActionButton icon={Undo2} label={t("webui.plugins.rollback")} disabled={!target.previous_generation} onClick={() => selectOperation("management.plugin.rollback", { runtime_id: target.id })} /><PluginActionButton icon={Trash2} label={t("webui.plugins.uninstall")} disabled={!bundle} onClick={() => selectOperation("management.plugin.uninstall", values)} /><PluginActionButton icon={History} label={t("webui.plugins.gc")} onClick={() => selectOperation("management.plugin.gc", { runtime_id: target.id })} /></CardContent>
    </Card>
  </div>;
}
