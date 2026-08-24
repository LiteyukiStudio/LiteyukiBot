import { useEffect, useState } from "react";
import { Cable, CircleAlert, ShieldCheck } from "lucide-react";
import { SurfaceCard } from "@/components/surface-card";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/i18n/locale";
import type { TopologyGraph } from "@/models/api";
import type { WebUiApi } from "@/services/webui-api";

export function TopologyGraphView({ api }: { api: WebUiApi }) {
  const { t } = useLocale();
  const [graph, setGraph] = useState<TopologyGraph | null>(null);
  useEffect(() => { void api.topologyGraph().then(setGraph); }, [api]);
  return <div className="webui-topology-graph"><header className="webui-plugin-header"><div><h2 className="webui-plugin-title"><Cable size={20} className="text-primary" />{t("webui.topology.title")}</h2></div></header><div className="grid gap-4 md:grid-cols-2">{graph?.nodes.length ? graph.nodes.map((node) => <SurfaceCard key={node.id}><CardHeader><CardTitle className="flex items-center gap-2 text-sm"><ShieldCheck size={16} className="text-primary" />{node.label}</CardTitle></CardHeader><CardContent className="grid gap-1 text-sm"><span>{node.kind}</span><strong>{node.state}</strong><span className="text-xs text-muted-foreground">{graph.edges.filter((edge) => edge.source === node.id || edge.target === node.id).length} connections</span></CardContent></SurfaceCard>) : <SurfaceCard><CardContent className="flex items-center gap-2 py-10 text-sm text-muted-foreground"><CircleAlert size={16} />{t("webui.topology.empty")}</CardContent></SurfaceCard>}</div></div>;
}
