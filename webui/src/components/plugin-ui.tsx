import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/i18n/locale";
import type { PluginGeneration, PluginTarget } from "@/models/api";
import { cn } from "@/lib/utils";

export function PluginStatePill({ value }: { value: string }) {
  const { t } = useLocale();
  const positive = new Set(["active", "ready", "running", "stable", "enabled", "healthy"]).has(value);
  const warning = new Set(["yanked", "starting", "recovering", "available", "experimental"]).has(value);
  return <Badge variant={positive ? "secondary" : warning ? "outline" : "destructive"} className={cn("capitalize", positive && "border-emerald-200 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300")}>{t(`webui.plugins.state.${value}`)}</Badge>;
}

export function PluginTargetSelect({
  targets,
  value,
  onChange,
  label,
  emptyLabel,
  className,
}: {
  targets: PluginTarget[];
  value: string;
  onChange: (value: string) => void;
  label: string;
  emptyLabel: string;
  className?: string;
}) {
  return <select aria-label={label} className={cn("webui-plugin-select", className)} value={value} onChange={(event) => onChange(event.target.value)}><option value="">{emptyLabel}</option>{targets.map((target) => <option value={target.id} key={target.id}>{target.id} · {target.kind}</option>)}</select>;
}

export function PluginGenerationPanel({ title, generation }: { title: string; generation: PluginGeneration | null }) {
  const { t } = useLocale();
  return <div className="webui-plugin-generation"><p className="webui-plugin-label">{title}</p>{generation ? <><p className="webui-plugin-generation-id">{generation.id}</p><p className="webui-plugin-muted">{generation.created_at}</p><div className="webui-plugin-badge-row">{generation.bundles.map((bundle) => <Badge key={bundle} variant={generation.disabled_roots.includes(bundle) ? "outline" : "secondary"} className="font-mono text-[10px]">{bundle}{generation.disabled_roots.includes(bundle) ? ` · ${t("webui.plugins.disabled")}` : ""}</Badge>)}</div><p className="webui-plugin-digest">{generation.index_digest ?? t("webui.plugins.legacy_generation")}</p></> : <p className="webui-plugin-empty-inline">{t("webui.plugins.none")}</p>}</div>;
}

export function PluginInfoGrid({ items }: { items: Array<{ label: string; value: string }> }) {
  return <div className="webui-plugin-info-grid">{items.map((item) => <PluginInfo key={item.label} {...item} />)}</div>;
}

export function PluginInfo({ label, value }: { label: string; value: string }) {
  return <div className="webui-plugin-info"><p className="webui-plugin-label">{label}</p><p className="webui-plugin-info-value">{value}</p></div>;
}

export function PluginActionButton({ icon: Icon, label, onClick, disabled = false }: { icon: LucideIcon; label: string; onClick: () => void; disabled?: boolean }) {
  return <Button variant="outline" size="sm" onClick={onClick} disabled={disabled}><Icon size={14} />{label}</Button>;
}

export function formatPluginBytes(value: number | null, exact: boolean, unavailableLabel = "size unavailable"): string {
  if (!exact || value === null) return unavailableLabel;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}
