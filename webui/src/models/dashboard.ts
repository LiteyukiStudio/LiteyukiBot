import type { Json, JsonObject, WebUiOperation, WebUiOperationRecord } from "@/models/api";

export type RuntimeView = { id: string; kind: string; state: string; protocol: string; activity: string };
export type PluginView = { id: string; name: string; version: string; state: string; provides: string[] };
export type LedgerView = { id: string; at: string; title: string; source: string; status: string; detail: string };
export type Dashboard = {
  instance: string;
  kernelState: string;
  version: string;
  runtimes: RuntimeView[];
  plugins: PluginView[];
  ledger: LedgerView[];
  operations: WebUiOperation[];
  audit: WebUiOperationRecord[];
  firstRun: boolean;
};

const record = (value: Json | undefined): JsonObject => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const string = (value: Json | undefined, fallback = "-"): string => typeof value === "string" ? value : fallback;
const list = (value: Json | undefined): Json[] => Array.isArray(value) ? value : [];

export function projectDashboard(bootstrap: JsonObject, ledger: JsonObject, catalog: WebUiOperation[], audit: WebUiOperationRecord[]): Dashboard {
  const snapshot = record(bootstrap.snapshot);
  const status = record(snapshot.status);
  const topology = record(snapshot.topology);
  const kernel = record(topology.kernel);
  const runtimes = list(topology.runtimes).map((item) => {
    const value = record(item); const health = record(value.health);
    return { id: string(value.id), kind: string(value.kind), state: string(health.state, string(value.state, "unknown")), protocol: string(health.protocol_version, "LYIP"), activity: string(health.last_heartbeat, "No activity") };
  });
  const plugins = list(topology.plugins).map((item) => {
    const value = record(item);
    return { id: string(value.id), name: string(value.name), version: string(value.version), state: string(value.state), provides: list(value.provides).map((entry) => string(entry)) };
  });
  const events = list(ledger.items).map((item) => {
    const value = record(item);
    return { id: string(value.id), at: string(value.at), title: string(value.title), source: string(value.source), status: string(value.status), detail: string(value.detail) };
  });
  return { instance: string(bootstrap.instance, "local"), kernelState: string(kernel.state, string(status.state, "unavailable")), version: string(kernel.version, string(status.version)), runtimes, plugins, ledger: events, operations: catalog, audit, firstRun: bootstrap.first_run === true };
}
