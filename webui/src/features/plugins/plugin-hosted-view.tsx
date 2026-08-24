import { Boxes, CircleCheck, CircleX } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PluginTargetPage } from "@/models/api";
import { useLocale } from "@/i18n/locale";

export function PluginHostedView({ targets }: { targets: PluginTargetPage | null }) {
  const { t } = useLocale();
  const items = targets?.items ?? [];
  return <div className="webui-plugin-view"><Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Boxes size={17} className="text-primary" />{t("webui.plugins.hosted")}</CardTitle></CardHeader><CardContent>{items.length === 0 ? <div className="webui-plugin-empty">{t("webui.plugins.no_targets")}</div> : <div className="webui-plugin-hosted-list">{items.map((target) => <section className="webui-plugin-hosted-target" key={target.id}><header><div><h3>{target.id}</h3><p>{target.kind}</p></div><Badge variant={target.state === "ready" ? "secondary" : "outline"}>{target.state}</Badge></header><div className="webui-plugin-hosted-bundles">{target.active_generation?.enabled_bundle_set.length ? target.active_generation.enabled_bundle_set.map((bundle) => <span key={bundle}><CircleCheck size={13} />{bundle}</span>) : <span className="text-muted-foreground"><CircleX size={13} />{t("webui.plugins.no_hosted_plugins")}</span>}</div></section>)}</div>}</CardContent></Card></div>;
}
