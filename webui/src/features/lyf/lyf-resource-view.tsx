import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, FileCode2, LockKeyhole } from "lucide-react";
import { useTheme } from "next-themes";
import { createLyfTokenizer, lyfThemeToken, type LyfTokenDocument, type LyfTokenizer } from "@liteyuki/lyf-textmate";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SurfaceCard } from "@/components/surface-card";
import { useLocale } from "@/i18n/locale";
import type { LyfResourcePage } from "@/models/api";
import { cn } from "@/lib/utils";

/**
 * Displays the daemon's read-only LYF resource projection and parser diagnostics.
 * @param props - One bounded resource page returned by the local API.
 * @returns A resource selector and source viewer.
 * @remarks Source is rendered as text inside `code`; this surface deliberately offers no write or execution action.
 */
export function LyfResourceView({ page }: { page: LyfResourcePage }) {
  const { t } = useLocale();
  const [selectedPath, setSelectedPath] = useState(page.items[0]?.path ?? "");
  const selected = useMemo(() => page.items.find((item) => item.path === selectedPath) ?? page.items[0], [page.items, selectedPath]);
  useEffect(() => { if (!page.items.some((item) => item.path === selectedPath)) setSelectedPath(page.items[0]?.path ?? ""); }, [page.items, selectedPath]);
  return <div className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
    <SurfaceCard>
      <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><FileCode2 size={16} />{t("webui.lyf.resources")}</CardTitle></CardHeader>
      <CardContent className="grid gap-1 p-2">{page.items.length === 0 ? <p className="p-3 text-sm text-muted-foreground">{t("webui.lyf.empty")}</p> : page.items.map((item) => <Button key={item.path} variant="ghost" className={cn("justify-start gap-2 truncate font-mono text-xs", selected?.path === item.path && "bg-muted")} onClick={() => setSelectedPath(item.path)}><FileCode2 size={14} />{item.path}</Button>)}</CardContent>
    </SurfaceCard>
    <SurfaceCard className="min-w-0">
      <CardHeader className="flex-row items-center justify-between gap-3"><CardTitle className="min-w-0 truncate font-mono text-sm">{selected?.path ?? t("webui.lyf.empty")}</CardTitle><Badge variant="outline" className="shrink-0 gap-1"><LockKeyhole size={13} />{t("webui.lyf.read_only")}</Badge></CardHeader>
      <CardContent className="grid gap-4">{selected ? <><TokenizedSource source={selected.source} /><div className="grid gap-2">{selected.diagnostics.length === 0 ? <p className="text-sm text-emerald-700">{t("webui.lyf.no_diagnostics")}</p> : selected.diagnostics.map((diagnostic, index) => <div className="flex items-start gap-2 border-t pt-2 text-sm" key={`${diagnostic.code}-${index}`}><AlertTriangle className="mt-0.5 shrink-0 text-amber-600" size={15} /><span><strong className="font-mono">{diagnostic.code}</strong> {diagnostic.message}</span></div>)}</div></> : <p className="text-sm text-muted-foreground">{t("webui.lyf.empty")}</p>}</CardContent>
    </SurfaceCard>
  </div>;
}

function TokenizedSource({ source }: { source: string }) {
  const { t } = useLocale();
  const { resolvedTheme } = useTheme();
  const [document, setDocument] = useState<LyfTokenDocument | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "fallback">("loading");
  const [error, setError] = useState<string | null>(null);
  const theme = resolvedTheme === "dark" ? "dark" : "light";

  useEffect(() => {
    const controller = new AbortController();
    let tokenizer: LyfTokenizer | null = null;
    setDocument(null);
    setError(null);
    setState("loading");
    void createLyfTokenizer().then((nextTokenizer) => {
      tokenizer = nextTokenizer;
      if (controller.signal.aborted) {
        nextTokenizer.dispose();
        return;
      }
      const nextDocument = nextTokenizer.tokenize(source, { signal: controller.signal });
      if (!controller.signal.aborted) {
        setDocument(nextDocument);
        setState("ready");
      }
    }).catch((cause: unknown) => {
      if (controller.signal.aborted) return;
      setError(cause instanceof Error ? cause.message : t("webui.lyf.tokenize_error"));
      setState("fallback");
    });
    return () => {
      controller.abort();
      tokenizer?.dispose();
    };
  }, [source, t]);

  return <div className="grid gap-2"><div className="flex min-h-5 items-center justify-between gap-2 text-xs text-muted-foreground" aria-live="polite">{state === "loading" ? <span>{t("webui.lyf.tokenizing")}</span> : state === "fallback" ? <span className="text-amber-700">{t("webui.lyf.plain_fallback")}</span> : <span>{t("webui.lyf.tokenized")}</span>}{error ? <span className="truncate" title={error}>{error}</span> : null}</div><pre className="min-h-[520px] max-h-[520px] overflow-auto rounded-md border bg-muted/25 p-4 text-xs leading-6"><code>{document ? <TokenLines document={document} theme={theme} /> : <PlainSource source={source} />}</code></pre></div>;
}

function TokenLines({ document, theme }: { document: LyfTokenDocument; theme: "light" | "dark" }) {
  return document.lines.map((line, index) => <span className="block min-h-[1.5rem]" key={index}><TokenLine line={line} theme={theme} />{index < document.lines.length - 1 ? "\n" : null}</span>);
}

function TokenLine({ line, theme }: { line: LyfTokenDocument["lines"][number]; theme: "light" | "dark" }) {
  let cursor = 0;
  const parts: ReactNode[] = [];
  line.tokens.forEach((token, index) => {
    if (token.startIndex > cursor) parts.push(<span key={`plain-${index}`}>{line.text.slice(cursor, token.startIndex)}</span>);
    const value = line.text.slice(token.startIndex, token.endIndex);
    const tokenStyle = lyfThemeToken(token.scopes, theme);
    parts.push(<span key={`token-${index}`} style={{ color: tokenStyle.foreground, fontStyle: tokenStyle.fontStyle === "italic" ? "italic" : undefined, fontWeight: tokenStyle.fontStyle === "bold" ? 700 : undefined, textDecoration: tokenStyle.fontStyle === "underline" ? "underline" : undefined }}>{value}</span>);
    cursor = token.endIndex;
  });
  if (cursor < line.text.length) parts.push(<span key="tail">{line.text.slice(cursor)}</span>);
  return parts;
}

function PlainSource({ source }: { source: string }) {
  return source.split(/\r\n?|\n/).map((line, index, lines) => <span className="block min-h-[1.5rem]" key={index}>{line}{index < lines.length - 1 ? "\n" : null}</span>);
}
