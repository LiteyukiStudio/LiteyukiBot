export type Workspace = "overview" | "events" | "topology" | "runtimes" | "plugins" | "functions" | "configuration";

export type DetailKind = "event" | "runtime" | "plugin" | "function";

export type DetailReference = {
  kind: DetailKind;
  id: string;
};

export type Severity = "healthy" | "attention" | "critical" | "neutral";

export type LedgerItem = {
  id: string;
  at: string;
  category: "event" | "action" | "operation" | "system";
  title: string;
  source: string;
  status: Severity;
  trace: string;
  detail: string;
};

export type RuntimeItem = {
  id: string;
  kind: string;
  state: "running" | "stopped" | "recovering";
  uptime: string;
  protocol: string;
  capabilityCount: number;
  activity: string;
};

export type PluginItem = {
  id: string;
  name: string;
  version: string;
  state: "enabled" | "disabled";
  capabilities: string[];
  surface?: PluginSurface;
};

export type FunctionItem = {
  id: string;
  source: string;
  state: "ready" | "attention";
  handlers: number;
  diagnostics: string;
};

export type PluginComponent = {
  id: string;
  kind: "metric" | "table" | "notice" | "operation_form" | "operation_result";
  label: string;
  value?: string;
  columns?: string[];
  rows?: string[][];
  operationId?: string;
};

export type PluginSurface = {
  id: string;
  title: string;
  icon: "activity" | "boxes" | "shield";
  components: PluginComponent[];
};

export type Operation = {
  id: string;
  label: string;
  description: string;
  target: string;
  impact: "standard" | "high";
};

export const ledger: LedgerItem[] = [
  {
    id: "evt_01J8A7H2", at: "09:42:18", category: "event", title: "Message event accepted", source: "onebot-primary", status: "healthy", trace: "tr_01J8A7H2", detail: "Accepted by the local event bus and delivered to two eligible handlers.",
  },
  {
    id: "op_01J8A7GQ", at: "09:41:52", category: "operation", title: "Plugin generation activated", source: "profile", status: "healthy", trace: "op_01J8A7GQ", detail: "The selected plugin generation became the active generation after validation.",
  },
  {
    id: "evt_01J8A7G9", at: "09:40:05", category: "action", title: "Action delivery delayed", source: "onebot-primary", status: "attention", trace: "tr_01J8A7G9", detail: "The receiving runtime reported a delayed acknowledgement. Delivery completed without retry.",
  },
  {
    id: "sys_01J8A6ZW", at: "09:34:12", category: "system", title: "Runtime heartbeat restored", source: "satori-edge", status: "healthy", trace: "rt_01J8A6ZW", detail: "The supervised runtime returned to its expected heartbeat interval.",
  },
];

export const runtimes: RuntimeItem[] = [
  { id: "onebot-primary", kind: "OneBot v11", state: "running", uptime: "2h 14m", protocol: "LYIP v5", capabilityCount: 6, activity: "128 events / min" },
  { id: "satori-edge", kind: "Satori v1", state: "recovering", uptime: "18m", protocol: "LYIP v5", capabilityCount: 5, activity: "Heartbeat recovering" },
  { id: "compat-v6", kind: "v6 compatibility", state: "stopped", uptime: "-", protocol: "LYIP v3", capabilityCount: 3, activity: "Stopped by configuration" },
];

export const plugins: PluginItem[] = [
  {
    id: "profile", name: "Profile", version: "0.4.0", state: "enabled", capabilities: ["profile.read", "profile.write"],
    surface: {
      id: "overview", title: "Profile activity", icon: "activity", components: [
        { id: "active", kind: "metric", label: "Active profiles", value: "12" },
        { id: "queue", kind: "metric", label: "Pending updates", value: "3" },
        { id: "recent", kind: "table", label: "Recent profile changes", columns: ["Profile", "State", "Updated"], rows: [["orion", "Ready", "09:41"], ["helios", "Ready", "09:32"], ["atlas", "Pending", "09:17"]] },
        { id: "refresh", kind: "operation_form", label: "Refresh profile index", operationId: "management.profile.refresh" },
      ],
    },
  },
  { id: "resources", name: "Resources", version: "0.3.1", state: "enabled", capabilities: ["resources.read"] },
  { id: "example", name: "Example extension", version: "0.1.0", state: "disabled", capabilities: ["example.read"] },
];

export const functions: FunctionItem[] = [
  { id: "message-normalizer", source: "resources/functions/normalize.lang", state: "ready", handlers: 4, diagnostics: "No static diagnostics" },
  { id: "profile-onboarding", source: "plugins/profile/onboarding.lang", state: "attention", handlers: 2, diagnostics: "One guarded branch is unreachable" },
];

export const operations: Operation[] = [
  { id: "runtime.restart", label: "Restart runtime", description: "Stops and starts the selected runtime in its supervised generation.", target: "onebot-primary", impact: "standard" },
  { id: "runtime.stop", label: "Stop runtime", description: "Stops the selected runtime. Its supervised process will remain stopped.", target: "satori-edge", impact: "high" },
  { id: "plugin.disable", label: "Disable plugin", description: "Withdraws the selected plugin generation and its WebUI surfaces.", target: "profile", impact: "standard" },
  { id: "plugin.rollback", label: "Rollback plugin", description: "Restores the previously verified plugin generation.", target: "profile", impact: "high" },
];
