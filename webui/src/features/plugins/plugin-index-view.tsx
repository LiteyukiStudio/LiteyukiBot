import { ArrowDown, ArrowUp, Check, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { PluginDiscoveryPage } from "@/models/api";
import { useLocale } from "@/i18n/locale";

export function PluginIndexView({ discovery, order, disabled, update }: { discovery: PluginDiscoveryPage | null; order: string[]; disabled: string[]; update: (order: string[], disabled: string[]) => void }) {
  const { t } = useLocale();
  const sources = [...(discovery?.sources ?? [])].sort((left, right) => (order.indexOf(left.id) < 0 ? 999 : order.indexOf(left.id)) - (order.indexOf(right.id) < 0 ? 999 : order.indexOf(right.id)));
  return <div className="webui-plugin-view"><header className="webui-plugin-index-header"><h3>{t("webui.plugins.index")}</h3></header><div className="webui-plugin-index-list">{sources.map((source, index) => { const isDisabled = disabled.includes(source.id); const move = (delta: number) => { const next = [...sources.map((item) => item.id)]; const target = index + delta; if (target < 0 || target >= next.length) return; [next[index], next[target]] = [next[target], next[index]]; update(next, disabled); }; return <div className="webui-plugin-index-row" key={source.id}><span className="webui-plugin-index-order">{index + 1}</span><div className="min-w-0"><strong>{source.id}</strong><p>{source.url}</p></div><Badge variant={source.cache_state === "cached" ? "secondary" : "outline"}>{source.cache_state}</Badge><div className="webui-plugin-index-actions"><Button variant="ghost" size="icon" aria-label={t("webui.plugins.index_move_up")} onClick={() => move(-1)} disabled={index === 0}><ArrowUp size={14} /></Button><Button variant="ghost" size="icon" aria-label={t("webui.plugins.index_move_down")} onClick={() => move(1)} disabled={index === sources.length - 1}><ArrowDown size={14} /></Button><Button variant="ghost" size="icon" aria-label={t(isDisabled ? "webui.plugins.index_enable" : "webui.plugins.index_disable")} onClick={() => update(order, isDisabled ? disabled.filter((item) => item !== source.id) : [...disabled, source.id])}>{isDisabled ? <X size={14} /> : <Check size={14} />}</Button></div></div>; })}</div></div>;
}
