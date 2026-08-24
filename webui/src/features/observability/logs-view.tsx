import { useEffect, useState } from "react";
import { SurfaceCard } from "@/components/surface-card";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useLocale } from "@/i18n/locale";
import type { WebUiApi } from "@/services/webui-api";
import type { WebUiLogsPage } from "@/models/api";

export function LogsView({ api }: { api: WebUiApi }) {
  const { t } = useLocale();
  const [page, setPage] = useState<WebUiLogsPage | null>(null);
  const [query, setQuery] = useState("");
  const load = () => void api.logs({ query }).then(setPage);
  useEffect(() => {
    load();
    const timer = window.setInterval(load, 1000);
    return () => window.clearInterval(timer);
  }, [api, query]);
  return <SurfaceCard><CardHeader><CardTitle>{t("webui.logs.title")}</CardTitle></CardHeader><CardContent className="grid gap-4"><Input className="ly-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("webui.logs.filter_query")} />{page?.diagnostics.length ? <p className="text-sm text-amber-700">{t("webui.logs.diagnostics")}: {page.diagnostics.join(", ")}</p> : null}<div className="grid divide-y">{page?.items.length ? page.items.map((item) => <article className="grid gap-1 py-3" key={item.id}><div className="flex flex-wrap gap-2 text-xs"><strong>{item.level}</strong><span className="text-muted-foreground">{item.component} · {item.at}</span></div><p className="m-0 break-words text-sm">{item.message}</p></article>) : <p className="py-10 text-center text-sm text-muted-foreground">{t("webui.logs.empty")}</p>}</div></CardContent></SurfaceCard>;
}
