import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Boxes, Cable, CheckCircle2, CircleAlert, CircleDot, FileClock, Play, RefreshCw, ShieldCheck, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SurfaceCard } from "@/components/surface-card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { WebUiApi, type JsonObject, type WebUiOperation } from "@/lib/api";
import { projectDashboard, type Dashboard } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { Sidebar, TopStatusBar, navigation, type Workspace } from "@/components/app-shell";
import { useLocale } from "@/i18n/locale";


function currentWorkspace(): Workspace {
  const value = window.location.hash.replace(/^#\//, "") as Workspace;
  return navigation.some((entry) => entry.id === value) ? value : "overview";
}

export function App() {
  const { locale, presentation, applyPresentation, t } = useLocale();
  const api = useMemo(() => new WebUiApi(), []);
  const [workspace, setWorkspace] = useState<Workspace>(currentWorkspace);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [operation, setOperation] = useState<WebUiOperation | null>(null);

  const reload = useCallback(async () => {
    try {
      setError(null);
      await api.initialize();
      setSessionReady(true);
      const [bootstrap, ledger, catalog, audit, resolvedPresentation] = await Promise.all([api.bootstrap(), api.ledger(), api.catalog(), api.audit(), api.presentation(locale)]);
      applyPresentation(resolvedPresentation);
      setDashboard(projectDashboard(bootstrap, ledger, catalog.operations, audit.items));
    } catch (cause) {
      setDashboard(null);
      setSessionReady(false);
      setError(cause instanceof Error ? cause.message : "webui.request_failed");
    }
  }, [api, applyPresentation, locale]);

  useEffect(() => { void reload(); }, [reload]);
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

  const navigate = (next: Workspace) => { window.location.hash = `#/${next}`; setWorkspace(next); setMenuOpen(false); };
  if (error) return <Unavailable error={error} retry={reload} />;
  if (!dashboard) return <Loading />;
  const pageTitle = t(navigation.find((entry) => entry.id === workspace)?.labelKey ?? "webui.nav.overview");
  return <TooltipProvider><div className="grid min-h-screen bg-background lg:grid-cols-[236px_minmax(0,1fr)]">
    <Sidebar active={workspace} webuiVersion={presentation?.webuiVersion ?? "-"} dashboard={dashboard} navigate={navigate} />
    <Sheet open={menuOpen} onOpenChange={setMenuOpen}><SheetContent side="left" className="w-72 p-0"><SheetHeader className="sr-only"><SheetTitle>Navigation</SheetTitle></SheetHeader><Sidebar active={workspace} webuiVersion={presentation?.webuiVersion ?? "-"} dashboard={dashboard} drawer navigate={navigate} /></SheetContent></Sheet>
    <div className="min-w-0"><TopStatusBar dashboard={dashboard} pageTitle={pageTitle} openNavigation={() => setMenuOpen(true)} refresh={() => void reload()} /><main className="px-4 py-6 sm:px-7 sm:py-7 lg:px-10 lg:py-6"><div className="mx-auto max-w-[1120px]"><section className="webui-workbench"><WorkspaceView workspace={workspace} dashboard={dashboard} openOperation={setOperation} /></section></div></main></div>
    <OperationDialog operation={operation} close={() => setOperation(null)} api={api} reload={reload} />
  </div></TooltipProvider>;
}

function WorkspaceView({ workspace, dashboard, openOperation }: { workspace: Workspace; dashboard: Dashboard; openOperation: (operation: WebUiOperation) => void }) {
  if (workspace === "overview") return <Overview dashboard={dashboard} openOperation={openOperation} />;
  if (workspace === "events") return <Ledger dashboard={dashboard} />;
  if (workspace === "topology") return <Topology dashboard={dashboard} />;
  if (workspace === "runtimes") return <Runtimes dashboard={dashboard} openOperation={openOperation} />;
  if (workspace === "plugins") return <Plugins dashboard={dashboard} />;
  return <Configuration dashboard={dashboard} />;
}

function Overview({ dashboard, openOperation }: { dashboard: Dashboard; openOperation: (operation: WebUiOperation) => void }) {
  const running = dashboard.runtimes.filter((runtime) => runtime.state === "ready").length;
  const unresolved = dashboard.audit.filter((record) => ["failed", "unknown"].includes(record.state)).length;
  const kernelReady = dashboard.kernelState === "ready";
  return <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_365px]"><div className={cn("webui-status-strip xl:col-span-2 flex min-h-14 flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 text-sm", !kernelReady && "webui-status-strip--attention")}>{kernelReady ? <CheckCircle2 className="text-emerald-600" size={18} /> : <CircleAlert className="text-amber-700" size={18} />}<strong>{kernelReady ? "Healthy" : `Kernel ${dashboard.kernelState}`}</strong><span className="text-muted-foreground">Active runtimes: {running} / {dashboard.runtimes.length}</span>{dashboard.operations[0] && <Button className="ml-auto rounded-lg bg-card text-foreground shadow-sm hover:bg-muted" variant="outline" size="sm" onClick={() => openOperation(dashboard.operations[0])}>New operation <Play size={14} /></Button>}</div><section className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:col-span-2"><Metric label="Active runtimes" value={String(running)} detail={`${dashboard.runtimes.length} configured`} /><Metric label="Enabled plugins" value={String(dashboard.plugins.length)} detail="loaded generations" /><Metric label="Operation records" value={String(dashboard.ledger.length)} detail="retained evidence" /><Metric label="Unresolved faults" value={String(unresolved)} detail={unresolved === 0 ? "none recorded" : "requires review"} emphasis={unresolved > 0} /></section><Ledger dashboard={dashboard} compact /><aside className="grid content-start gap-4"><RuntimeHealth dashboard={dashboard} /><RecentEvidence dashboard={dashboard} /></aside></div>;
}

function Metric({ label, value, detail, emphasis = false }: { label: string; value: string; detail: string; emphasis?: boolean }) { return <SurfaceCard><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><strong className={cn("mt-2 block font-mono text-[26px] font-semibold", emphasis && "text-amber-600")}>{value}</strong><span className="mt-1 block text-[11px] text-muted-foreground">{detail}</span></CardContent></SurfaceCard>; }
function Ledger({ dashboard, compact = false }: { dashboard: Dashboard; compact?: boolean }) { return <SurfaceCard className={cn(compact && "min-h-[382px]")}><CardHeader className="flex-row items-start justify-between px-5 pt-5"><CardTitle className="text-sm font-semibold">Operation ledger</CardTitle></CardHeader><CardContent className="px-5 pb-5">{dashboard.ledger.length === 0 ? <Empty label="No retained operation records." /> : <ScrollArea className="max-h-[310px]"><Table><TableHeader><TableRow><TableHead>Operation</TableHead><TableHead>State</TableHead><TableHead className="hidden sm:table-cell">Updated</TableHead></TableRow></TableHeader><TableBody>{dashboard.ledger.map((item) => <TableRow key={item.id}><TableCell><div><p className="font-medium">{item.title}</p><p className="font-mono text-xs text-muted-foreground">{item.source}</p></div></TableCell><TableCell><State value={item.status} /></TableCell><TableCell className="hidden font-mono text-xs text-muted-foreground sm:table-cell">{item.at}</TableCell></TableRow>)}</TableBody></Table></ScrollArea>}</CardContent></SurfaceCard>; }
function RuntimeHealth({ dashboard }: { dashboard: Dashboard }) { return <SurfaceCard className="min-h-[190px]"><CardHeader className="px-4 pt-4"><CardTitle className="text-sm font-semibold">Runtime health</CardTitle></CardHeader><CardContent className="px-4 pb-3">{dashboard.runtimes.length === 0 ? <Empty label="No supervised runtimes." /> : <div className="grid">{dashboard.runtimes.slice(0, 4).map((runtime) => <div className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-2 border-t py-3 first:border-t-0" key={runtime.id}><span className="webui-runtime-mark"><Cable size={15} /></span><div className="min-w-0"><p className="truncate text-xs font-semibold">{runtime.id}</p><p className="mt-0.5 truncate text-[11px] text-muted-foreground">{runtime.kind} · {runtime.activity}</p></div><State value={runtime.state} /></div>)}</div>}</CardContent></SurfaceCard>; }
function RecentEvidence({ dashboard }: { dashboard: Dashboard }) { const evidence = dashboard.audit.slice(0, 3); return <SurfaceCard className="min-h-[150px]"><CardHeader className="px-4 pt-4"><CardTitle className="text-sm font-semibold">Recent evidence</CardTitle></CardHeader><CardContent className="px-4 pb-3">{evidence.length === 0 ? <Empty label="No retained audit records." /> : evidence.map((record) => <div className="grid grid-cols-[18px_minmax(0,1fr)_16px] items-center gap-2 border-t py-3" key={record.id}><CircleDot className="text-amber-500" size={16} /><div className="min-w-0"><p className="truncate text-xs font-semibold">{record.operation}</p><p className="mt-0.5 truncate text-[11px] text-muted-foreground">{record.target} · {record.updated_at}</p></div><ArrowRight className="text-muted-foreground" size={15} /></div>)}</CardContent></SurfaceCard>; }
function Runtimes({ dashboard, openOperation }: { dashboard: Dashboard; openOperation: (operation: WebUiOperation) => void }) { return <Card><CardHeader className="flex-row items-start justify-between"><CardTitle>Supervised runtimes</CardTitle>{dashboard.operations[0] && <Button size="sm" onClick={() => openOperation(dashboard.operations[0])}>Queue action</Button>}</CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>Runtime</TableHead><TableHead>State</TableHead><TableHead className="hidden md:table-cell">Protocol</TableHead><TableHead className="hidden md:table-cell">Activity</TableHead></TableRow></TableHeader><TableBody>{dashboard.runtimes.map((runtime) => <TableRow key={runtime.id}><TableCell><p className="font-medium">{runtime.id}</p><p className="text-xs text-muted-foreground">{runtime.kind}</p></TableCell><TableCell><State value={runtime.state} /></TableCell><TableCell className="hidden font-mono text-xs md:table-cell">{runtime.protocol}</TableCell><TableCell className="hidden text-xs text-muted-foreground md:table-cell">{runtime.activity}</TableCell></TableRow>)}</TableBody></Table></CardContent></Card>; }
function Plugins({ dashboard }: { dashboard: Dashboard }) { return <Card><CardHeader><CardTitle>Plugin generations</CardTitle></CardHeader><CardContent><div className="grid gap-3 md:grid-cols-2">{dashboard.plugins.map((plugin) => <Card key={plugin.id} className="bg-muted/30 shadow-none"><CardContent className="p-4"><div className="flex items-start justify-between gap-2"><div><p className="font-medium">{plugin.name}</p><p className="font-mono text-xs text-muted-foreground">{plugin.id} · {plugin.version}</p></div><State value={plugin.state} /></div><div className="mt-4 flex flex-wrap gap-1">{plugin.provides.slice(0, 4).map((service) => <Badge key={service} variant="secondary" className="font-mono text-[10px]">{service}</Badge>)}</div></CardContent></Card>)}</div>{dashboard.plugins.length === 0 && <Empty label="No plugins are active in this instance." />}</CardContent></Card>; }
function Topology({ dashboard }: { dashboard: Dashboard }) { return <div className="grid gap-4 md:grid-cols-2"><TopologyCard icon={ShieldCheck} title="Kernel" rows={[[dashboard.version, dashboard.kernelState]]} /><TopologyCard icon={Cable} title="Runtimes" rows={dashboard.runtimes.map((runtime) => [runtime.id, runtime.state])} /><TopologyCard icon={Boxes} title="Plugins" rows={dashboard.plugins.map((plugin) => [plugin.id, plugin.state])} /><TopologyCard icon={FileClock} title="Audit" rows={[[`${dashboard.audit.length} records`, "retained"]]} /></div>; }
function TopologyCard({ icon: Icon, title, rows }: { icon: typeof ShieldCheck; title: string; rows: string[][] }) { return <Card><CardHeader><CardTitle className="flex items-center gap-2 text-sm"><Icon size={16} className="text-primary" />{title}</CardTitle></CardHeader><CardContent className="grid gap-2">{rows.map(([label, state]) => <div key={label} className="flex items-center justify-between rounded-md bg-muted/45 px-3 py-2 text-sm"><span className="font-mono text-xs">{label}</span><State value={state} /></div>)}</CardContent></Card>; }
function Configuration({ dashboard }: { dashboard: Dashboard }) { return <Card><CardHeader><CardTitle>Instance configuration</CardTitle></CardHeader><CardContent className="grid divide-y"><Setting label="Instance" value={dashboard.instance} /><Setting label="Kernel" value={dashboard.version} /><Setting label="WebUI transport" value="loopback only" /><Setting label="Operation owner" value="instance daemon" /></CardContent></Card>; }
function Setting({ label, value }: { label: string; value: string }) { return <div className="grid gap-1 py-4 sm:grid-cols-[180px_1fr]"><span className="text-sm text-muted-foreground">{label}</span><strong className="font-mono text-sm">{value}</strong></div>; }
function State({ value }: { value: string }) { const positive = ["ready", "running", "enabled", "healthy", "succeeded"].includes(value); const warning = ["attention", "recovering", "queued", "running"].includes(value); return <Badge variant={positive ? "secondary" : warning ? "outline" : "destructive"} className={cn("capitalize", positive && "border-emerald-200 bg-emerald-50 text-emerald-700")}>{value}</Badge>; }
function Empty({ label }: { label: string }) { return <div className="grid min-h-32 place-items-center border-t text-sm text-muted-foreground">{label}</div>; }
function Loading() { return <main className="grid min-h-screen place-items-center"><div className="w-[min(440px,90vw)] space-y-3"><Skeleton className="h-7 w-44" /><Skeleton className="h-28 w-full" /><Skeleton className="h-48 w-full" /></div></main>; }
function Unavailable({ error, retry }: { error: string; retry: () => Promise<void> }) { return <main className="grid min-h-screen place-items-center p-5"><Card className="w-full max-w-md"><CardHeader><CircleAlert className="mb-2 text-destructive" /><CardTitle>Local service unavailable</CardTitle><CardDescription>The WebUI could not read the running daemon.</CardDescription></CardHeader><CardContent className="flex items-center justify-between gap-3"><code className="text-xs text-muted-foreground">{error}</code><Button onClick={() => void retry()}><RefreshCw size={15} />Retry</Button></CardContent></Card></main>; }
function OperationDialog({ operation, close, api, reload }: { operation: WebUiOperation | null; close: () => void; api: WebUiApi; reload: () => Promise<void> }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => { setValues({}); setConfirmation(""); }, [operation]);
  if (!operation) return null;
  const schema = operation.input_schema;
  const properties = schema.properties && typeof schema.properties === "object" && !Array.isArray(schema.properties) ? schema.properties as JsonObject : {};
  const required = Array.isArray(schema.required) ? schema.required.filter((field): field is string => typeof field === "string") : [];
  const fields = Object.entries(properties).filter(([, definition]) => typeof definition === "object" && definition !== null && !Array.isArray(definition));
  const targetField = operation.target_input_field ?? required[0] ?? "target";
  const target = values[targetField] ?? "";
  const canSubmit = target.trim().length > 0 && required.every((field) => values[field]?.trim()) && (operation.impact !== "high" || confirmation === target);
  const submit = async () => {
    if (!canSubmit) return;
    setPending(true);
    try {
      await api.submit(operation, target, values, true);
      toast.success("Operation queued");
      close();
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Operation could not be queued");
    } finally { setPending(false); }
  };
  return <Dialog open onOpenChange={(open) => !open && close()}><DialogContent><DialogHeader><DialogTitle>{operation.id}</DialogTitle><DialogDescription>Operation input is schema-validated and recorded by the daemon before the worker can execute it.</DialogDescription></DialogHeader><div className="grid gap-3">{fields.map(([field, definition]) => {
    const details = definition as JsonObject;
    const requiredField = required.includes(field);
    return <div key={field} className="grid gap-2"><label className="text-sm font-medium" htmlFor={`operation-${field}`}>{field}{requiredField && <span className="text-destructive"> *</span>}</label><Input id={`operation-${field}`} value={values[field] ?? ""} onChange={(event) => setValues((current) => ({ ...current, [field]: event.target.value }))} placeholder={typeof details.description === "string" ? details.description : `Enter ${field}`} />{field === targetField && operation.confirmation === "target" && <p className="text-xs text-muted-foreground">High-impact operations require the exact target confirmation.</p>}</div>;
  })}{operation.impact === "high" && <div className="grid gap-2"><label className="text-sm font-medium" htmlFor="operation-confirmation">Confirm target</label><Input id="operation-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="Type the exact target identifier" /></div>}</div><DialogFooter><Button variant="outline" onClick={close}>Cancel</Button><Button disabled={!canSubmit || pending} onClick={() => void submit()}>{pending ? "Queueing" : "Queue operation"}</Button></DialogFooter></DialogContent></Dialog>;
}
