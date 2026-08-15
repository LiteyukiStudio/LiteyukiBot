import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Boxes, Cable, CheckCircle2, ChevronRight, CircleAlert, Cog, FileClock, Menu, Network, Play, Radio, RefreshCw, ShieldCheck, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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

type Workspace = "overview" | "events" | "topology" | "runtimes" | "plugins" | "configuration";
const navigation: { id: Workspace; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "Overview", icon: Activity }, { id: "events", label: "Ledger", icon: Radio },
  { id: "topology", label: "Topology", icon: Network }, { id: "runtimes", label: "Runtimes", icon: Cable },
  { id: "plugins", label: "Plugins", icon: Boxes }, { id: "configuration", label: "Configuration", icon: Cog },
];

function currentWorkspace(): Workspace {
  const value = window.location.hash.replace(/^#\//, "") as Workspace;
  return navigation.some((entry) => entry.id === value) ? value : "overview";
}

export function App() {
  const api = useMemo(() => new WebUiApi(), []);
  const [workspace, setWorkspace] = useState<Workspace>(currentWorkspace);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [dismissFirstRun, setDismissFirstRun] = useState(false);
  const [operation, setOperation] = useState<WebUiOperation | null>(null);

  const reload = useCallback(async () => {
    try {
      setError(null);
      await api.initialize();
      setSessionReady(true);
      const [bootstrap, ledger, catalog, audit] = await Promise.all([api.bootstrap(), api.ledger(), api.catalog(), api.audit()]);
      setDashboard(projectDashboard(bootstrap, ledger, catalog.operations, audit.items));
    } catch (cause) {
      setDashboard(null);
      setSessionReady(false);
      setError(cause instanceof Error ? cause.message : "webui.request_failed");
    }
  }, [api]);

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
  if (dashboard.firstRun && !dismissFirstRun) return <FirstRun instance={dashboard.instance} open={() => { setDismissFirstRun(true); setWorkspace("runtimes"); window.location.hash = "#/runtimes"; }} />;
  return <TooltipProvider><div className="grid min-h-screen lg:grid-cols-[248px_minmax(0,1fr)]">
    <Sidebar active={workspace} dashboard={dashboard} navigate={navigate} />
    <Sheet open={menuOpen} onOpenChange={setMenuOpen}><SheetContent side="left" className="w-72 p-0"><SheetHeader className="sr-only"><SheetTitle>Navigation</SheetTitle></SheetHeader><Sidebar active={workspace} dashboard={dashboard} navigate={navigate} /></SheetContent></Sheet>
    <main className="min-w-0 p-4 sm:p-7 lg:p-10"><div className="mx-auto max-w-7xl">
      <header className="mb-7 flex items-start justify-between gap-3"><div className="flex items-start gap-3"><Button className="lg:hidden" variant="outline" size="icon" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu /></Button><div><p className="mb-1 font-mono text-xs font-semibold tracking-[.08em] text-muted-foreground">LOCAL INSTANCE</p><h1 className="text-2xl font-semibold tracking-normal">{navigation.find((entry) => entry.id === workspace)?.label}</h1></div></div><Tooltip><TooltipTrigger asChild><Button variant="outline" size="icon" onClick={() => void reload()} aria-label="Refresh"><RefreshCw size={16} /></Button></TooltipTrigger><TooltipContent>Refresh snapshot</TooltipContent></Tooltip></header>
      <WorkspaceView workspace={workspace} dashboard={dashboard} openOperation={setOperation} />
    </div></main>
    <OperationDialog operation={operation} close={() => setOperation(null)} api={api} reload={reload} />
  </div></TooltipProvider>;
}

function Sidebar({ active, dashboard, navigate }: { active: Workspace; dashboard: Dashboard; navigate: (workspace: Workspace) => void }) {
  return <aside className="flex h-full min-h-screen flex-col border-r bg-card px-3 py-5"><div className="mb-8 flex items-center gap-3 px-2"><div className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground"><ShieldCheck size={18} /></div><div><strong className="block text-sm">LiteyukiBot</strong><span className="text-xs text-muted-foreground">Control surface</span></div></div><nav className="grid gap-1">{navigation.map(({ id, label, icon: Icon }) => <Button key={id} variant={active === id ? "secondary" : "ghost"} className="justify-start" onClick={() => navigate(id)}><Icon size={16} />{label}</Button>)}</nav><div className="mt-auto border-t px-2 pt-4 text-xs text-muted-foreground"><div className="mb-1 flex items-center gap-2"><span className="size-2 rounded-full bg-emerald-500" />{dashboard.kernelState}</div><span className="font-mono">{dashboard.instance}</span></div></aside>;
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
  return <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_360px]"><div className="xl:col-span-2 flex flex-wrap items-center gap-3 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm"><CheckCircle2 className="text-emerald-600" size={18} /><strong>Kernel {dashboard.kernelState}</strong><span className="text-muted-foreground">{running} ready runtimes</span>{dashboard.operations[0] && <Button className="ml-auto" size="sm" onClick={() => openOperation(dashboard.operations[0])}><Play size={14} />Run operation</Button>}</div><section className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:col-span-2"><Metric label="Runtimes" value={String(dashboard.runtimes.length)} detail={`${running} ready`} /><Metric label="Plugins" value={String(dashboard.plugins.length)} detail="loaded generations" /><Metric label="Operations" value={String(dashboard.audit.length)} detail="retained records" /><Metric label="Protocol" value={dashboard.version} detail="kernel version" /></section><Ledger dashboard={dashboard} compact /><Card><CardHeader><CardTitle className="text-sm">Runtime health</CardTitle><CardDescription>Current supervised processes</CardDescription></CardHeader><CardContent className="grid gap-1">{dashboard.runtimes.slice(0, 5).map((runtime) => <div key={runtime.id} className="flex items-center justify-between rounded-md px-2 py-2"><div><p className="text-sm font-medium">{runtime.id}</p><p className="text-xs text-muted-foreground">{runtime.kind}</p></div><State value={runtime.state} /></div>)}</CardContent></Card></div>;
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) { return <Card><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><strong className="mt-2 block font-mono text-2xl font-semibold">{value}</strong><span className="mt-1 block text-xs text-muted-foreground">{detail}</span></CardContent></Card>; }
function Ledger({ dashboard, compact = false }: { dashboard: Dashboard; compact?: boolean }) { return <Card className={compact ? "" : ""}><CardHeader><CardTitle className="text-sm">Operation ledger</CardTitle><CardDescription>Daemon-owned, redacted management evidence</CardDescription></CardHeader><CardContent>{dashboard.ledger.length === 0 ? <Empty label="No retained operation records." /> : <ScrollArea className="max-h-[440px]"><Table><TableHeader><TableRow><TableHead>Operation</TableHead><TableHead>State</TableHead><TableHead className="hidden sm:table-cell">Updated</TableHead></TableRow></TableHeader><TableBody>{dashboard.ledger.map((item) => <TableRow key={item.id}><TableCell><div><p className="font-medium">{item.title}</p><p className="font-mono text-xs text-muted-foreground">{item.source}</p></div></TableCell><TableCell><State value={item.status} /></TableCell><TableCell className="hidden font-mono text-xs text-muted-foreground sm:table-cell">{item.at}</TableCell></TableRow>)}</TableBody></Table></ScrollArea>}</CardContent></Card>; }
function Runtimes({ dashboard, openOperation }: { dashboard: Dashboard; openOperation: (operation: WebUiOperation) => void }) { return <Card><CardHeader className="flex-row items-start justify-between"><div><CardTitle>Supervised runtimes</CardTitle><CardDescription>Lifecycle actions are queued through the daemon ledger.</CardDescription></div>{dashboard.operations[0] && <Button size="sm" onClick={() => openOperation(dashboard.operations[0])}>Queue action</Button>}</CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>Runtime</TableHead><TableHead>State</TableHead><TableHead className="hidden md:table-cell">Protocol</TableHead><TableHead className="hidden md:table-cell">Activity</TableHead></TableRow></TableHeader><TableBody>{dashboard.runtimes.map((runtime) => <TableRow key={runtime.id}><TableCell><p className="font-medium">{runtime.id}</p><p className="text-xs text-muted-foreground">{runtime.kind}</p></TableCell><TableCell><State value={runtime.state} /></TableCell><TableCell className="hidden font-mono text-xs md:table-cell">{runtime.protocol}</TableCell><TableCell className="hidden text-xs text-muted-foreground md:table-cell">{runtime.activity}</TableCell></TableRow>)}</TableBody></Table></CardContent></Card>; }
function Plugins({ dashboard }: { dashboard: Dashboard }) { return <Card><CardHeader><CardTitle>Plugin generations</CardTitle><CardDescription>Plugin WebUI contributions remain declarative and host-rendered.</CardDescription></CardHeader><CardContent><div className="grid gap-3 md:grid-cols-2">{dashboard.plugins.map((plugin) => <Card key={plugin.id} className="bg-muted/30 shadow-none"><CardContent className="p-4"><div className="flex items-start justify-between gap-2"><div><p className="font-medium">{plugin.name}</p><p className="font-mono text-xs text-muted-foreground">{plugin.id} · {plugin.version}</p></div><State value={plugin.state} /></div><div className="mt-4 flex flex-wrap gap-1">{plugin.provides.slice(0, 4).map((service) => <Badge key={service} variant="secondary" className="font-mono text-[10px]">{service}</Badge>)}</div></CardContent></Card>)}</div>{dashboard.plugins.length === 0 && <Empty label="No plugins are active in this instance." />}</CardContent></Card>; }
function Topology({ dashboard }: { dashboard: Dashboard }) { return <div className="grid gap-4 md:grid-cols-2"><TopologyCard icon={ShieldCheck} title="Kernel" rows={[[dashboard.version, dashboard.kernelState]]} /><TopologyCard icon={Cable} title="Runtimes" rows={dashboard.runtimes.map((runtime) => [runtime.id, runtime.state])} /><TopologyCard icon={Boxes} title="Plugins" rows={dashboard.plugins.map((plugin) => [plugin.id, plugin.state])} /><TopologyCard icon={FileClock} title="Audit" rows={[[`${dashboard.audit.length} records`, "retained"]]} /></div>; }
function TopologyCard({ icon: Icon, title, rows }: { icon: typeof ShieldCheck; title: string; rows: string[][] }) { return <Card><CardHeader><CardTitle className="flex items-center gap-2 text-sm"><Icon size={16} className="text-primary" />{title}</CardTitle></CardHeader><CardContent className="grid gap-2">{rows.map(([label, state]) => <div key={label} className="flex items-center justify-between rounded-md bg-muted/45 px-3 py-2 text-sm"><span className="font-mono text-xs">{label}</span><State value={state} /></div>)}</CardContent></Card>; }
function Configuration({ dashboard }: { dashboard: Dashboard }) { return <Card><CardHeader><CardTitle>Instance configuration</CardTitle><CardDescription>This view exposes configuration metadata only. Writes remain explicit management operations.</CardDescription></CardHeader><CardContent className="grid divide-y"><Setting label="Instance" value={dashboard.instance} /><Setting label="Kernel" value={dashboard.version} /><Setting label="WebUI transport" value="loopback only" /><Setting label="Operation owner" value="instance daemon" /></CardContent></Card>; }
function Setting({ label, value }: { label: string; value: string }) { return <div className="grid gap-1 py-4 sm:grid-cols-[180px_1fr]"><span className="text-sm text-muted-foreground">{label}</span><strong className="font-mono text-sm">{value}</strong></div>; }
function State({ value }: { value: string }) { const positive = ["ready", "running", "enabled", "healthy", "succeeded"].includes(value); const warning = ["attention", "recovering", "queued", "running"].includes(value); return <Badge variant={positive ? "secondary" : warning ? "outline" : "destructive"} className={cn("capitalize", positive && "border-emerald-200 bg-emerald-50 text-emerald-700")}>{value}</Badge>; }
function Empty({ label }: { label: string }) { return <div className="grid min-h-32 place-items-center border-t text-sm text-muted-foreground">{label}</div>; }
function Loading() { return <main className="grid min-h-screen place-items-center"><div className="w-[min(440px,90vw)] space-y-3"><Skeleton className="h-7 w-44" /><Skeleton className="h-28 w-full" /><Skeleton className="h-48 w-full" /></div></main>; }
function Unavailable({ error, retry }: { error: string; retry: () => Promise<void> }) { return <main className="grid min-h-screen place-items-center p-5"><Card className="w-full max-w-md"><CardHeader><CircleAlert className="mb-2 text-destructive" /><CardTitle>Local service unavailable</CardTitle><CardDescription>The WebUI could not read the running daemon.</CardDescription></CardHeader><CardContent className="flex items-center justify-between gap-3"><code className="text-xs text-muted-foreground">{error}</code><Button onClick={() => void retry()}><RefreshCw size={15} />Retry</Button></CardContent></Card></main>; }
function FirstRun({ instance, open }: { instance: string; open: () => void }) { return <main className="grid min-h-screen place-items-center p-5"><Card className="w-full max-w-xl"><CardHeader><CardTitle>Set up {instance}</CardTitle><CardDescription>No runnable runtime is configured yet. Create the first runtime through an explicit local management operation.</CardDescription></CardHeader><CardContent><Button onClick={open}>Open runtimes <ChevronRight size={15} /></Button></CardContent></Card></main>; }
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
