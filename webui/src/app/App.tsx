import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CircleAlert, RefreshCw } from "lucide-react";

import { Sidebar, TopStatusBar } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useLocale, useLocaleActions } from "@/i18n/locale";
import { projectDashboard, type Dashboard } from "@/models/dashboard";
import { isWorkspace, type Workspace } from "@/models/workspace";
import { WebUiApi } from "@/services/webui-api";

const workspaceViewModule = import("@/features/workspaces/workspace-view");
const WorkspaceView = lazy(() => workspaceViewModule.then(({ WorkspaceView: View }) => ({ default: View })));

function currentWorkspace(): Workspace {
  const value = window.location.hash.replace(/^#\//, "");
  return isWorkspace(value) ? value : "overview";
}

export function App() {
  const { applyPresentation, getLocale } = useLocaleActions();
  const api = useMemo(() => new WebUiApi(), []);
  const [workspace, setWorkspace] = useState<Workspace>(currentWorkspace);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const reloadSequence = useRef(0);

  const reload = useCallback(async (requestedLocale?: string) => {
    const requestId = reloadSequence.current + 1;
    reloadSequence.current = requestId;
    try {
      await api.initialize();
      const [bootstrap, ledger, catalog, audit, resolvedPresentation] = await Promise.all([api.bootstrap(), api.ledger(), api.catalog(), api.audit(), api.presentation(requestedLocale ?? getLocale())]);
      if (requestId !== reloadSequence.current) return;
      setError(null);
      setSessionReady(true);
      applyPresentation(resolvedPresentation);
      setDashboard(projectDashboard(bootstrap, ledger, catalog.operations, audit.items));
    } catch (cause) {
      if (requestId !== reloadSequence.current) return;
      setDashboard(null);
      setSessionReady(false);
      setError(cause instanceof Error ? cause.message : "webui.request_failed");
    }
  }, [api, applyPresentation, getLocale]);

  useEffect(() => {
    const onHash = () => setWorkspace(currentWorkspace());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (!sessionReady) return;
    const source = api.events((type) => { if (type !== "heartbeat") void reload(); }, () => undefined);
    return () => source.close();
  }, [api, reload, sessionReady]);

  const navigate = useCallback((next: Workspace) => { window.location.hash = `#/${next}`; setWorkspace(next); setMenuOpen(false); }, []);
  const openNavigation = useCallback(() => setMenuOpen(true), []);
  const refresh = useCallback(() => void reload(), [reload]);
  return <><PresentationSynchronizer reload={reload} />{error ? <Unavailable error={error} retry={reload} /> : !dashboard ? <Loading /> : <TooltipProvider><div className="grid min-h-screen bg-background lg:grid-cols-[236px_minmax(0,1fr)]"><Sidebar active={workspace} dashboard={dashboard} navigate={navigate} /><Sheet open={menuOpen} onOpenChange={setMenuOpen}><SheetContent side="left" className="w-72 p-0"><SheetHeader className="sr-only"><SheetTitle>Navigation</SheetTitle></SheetHeader><Sidebar active={workspace} dashboard={dashboard} drawer navigate={navigate} /></SheetContent></Sheet><div className="min-w-0"><TopStatusBar dashboard={dashboard} workspace={workspace} openNavigation={openNavigation} refresh={refresh} /><main className="px-4 py-6 sm:px-7 sm:py-7 lg:px-10 lg:pb-6 lg:pt-0"><section className="webui-workspace-base mx-auto max-w-[1120px]"><Suspense fallback={<Skeleton className="h-[382px] w-full" />}><WorkspaceView workspace={workspace} dashboard={dashboard} api={api} reload={reload} /></Suspense></section></main></div></div></TooltipProvider>}</>;
}

function PresentationSynchronizer({ reload }: { reload: (locale: string) => Promise<void> }) {
  const { locale } = useLocale();
  useEffect(() => { void reload(locale); }, [locale, reload]);
  return null;
}

function Loading() {
  return <main className="grid min-h-screen place-items-center"><div className="w-[min(440px,90vw)] space-y-3"><Skeleton className="h-7 w-44" /><Skeleton className="h-28 w-full" /><Skeleton className="h-48 w-full" /></div></main>;
}

function Unavailable({ error, retry }: { error: string; retry: () => Promise<void> }) {
  const { t } = useLocale();
  return <main className="grid min-h-screen place-items-center p-5"><Card className="w-full max-w-md"><CardHeader><CircleAlert className="mb-2 text-destructive" /><CardTitle>{t("webui.error.unavailable")}</CardTitle><CardDescription>{t("webui.error.unavailable_detail")}</CardDescription></CardHeader><CardContent className="flex items-center justify-between gap-3"><code className="text-xs text-muted-foreground">{error}</code><Button onClick={() => void retry()}><RefreshCw size={15} />{t("webui.action.retry")}</Button></CardContent></Card></main>;
}
