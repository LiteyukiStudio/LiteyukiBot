import { useMemo, useState } from "react";
import { AlertTriangle, FileCode2, LockKeyhole } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/i18n/locale";
import type { LyfResourcePage } from "@/models/api";
import { cn } from "@/lib/utils";

export function LyfResourceView({ page }: { page: LyfResourcePage }) {
  const { t } = useLocale();
  const [selectedPath, setSelectedPath] = useState(page.items[0]?.path ?? "");
  const selected = useMemo(() => page.items.find((item) => item.path === selectedPath) ?? page.items[0], [page.items, selectedPath]);
  return <div className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><FileCode2 size={16} />{t("webui.lyf.resources")}</CardTitle></CardHeader>
      <CardContent className="grid gap-1 p-2">{page.items.length === 0 ? <p className="p-3 text-sm text-muted-foreground">{t("webui.lyf.empty")}</p> : page.items.map((item) => <Button key={item.path} variant="ghost" className={cn("justify-start gap-2 truncate font-mono text-xs", selected?.path === item.path && "bg-muted")} onClick={() => setSelectedPath(item.path)}><FileCode2 size={14} />{item.path}</Button>)}</CardContent>
    </Card>
    <Card className="min-w-0">
      <CardHeader className="flex-row items-center justify-between gap-3"><CardTitle className="min-w-0 truncate font-mono text-sm">{selected?.path ?? t("webui.lyf.empty")}</CardTitle><Badge variant="outline" className="shrink-0 gap-1"><LockKeyhole size={13} />{t("webui.lyf.read_only")}</Badge></CardHeader>
      <CardContent className="grid gap-4">{selected ? <><pre className="max-h-[520px] overflow-auto rounded-md border bg-muted/25 p-4 text-xs leading-6"><code>{selected.source}</code></pre><div className="grid gap-2">{selected.diagnostics.length === 0 ? <p className="text-sm text-emerald-700">{t("webui.lyf.no_diagnostics")}</p> : selected.diagnostics.map((diagnostic, index) => <div className="flex items-start gap-2 border-t pt-2 text-sm" key={`${diagnostic.code}-${index}`}><AlertTriangle className="mt-0.5 shrink-0 text-amber-600" size={15} /><span><strong className="font-mono">{diagnostic.code}</strong> {diagnostic.message}</span></div>)}</div></> : <p className="text-sm text-muted-foreground">{t("webui.lyf.empty")}</p>}</CardContent>
    </Card>
  </div>;
}
