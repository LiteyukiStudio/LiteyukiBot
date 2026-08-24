export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type JsonObject = Record<string, Json>;

export type WebUiOperation = {
  id: string;
  input_schema: JsonObject;
  impact: "standard" | "high" | "none";
  confirmation: "explicit" | "target" | "none";
  target: string;
  target_input_field: string | null;
};

export type WebUiOperationRecord = {
  id: string;
  operation: string;
  target: string;
  state: string;
  result_code: string | null;
  created_at: string;
  updated_at: string;
};

export type WebUiPresentation = {
  locale: string;
  locales: string[];
  messages: Record<string, string>;
  webui_version: string;
};

export type EventDeliveryFilters = Partial<Record<"state" | "topic" | "source" | "target" | "failure", string>>;

export type EventDeliveryBridge = {
  id: string;
  state: string;
  session_state?: string;
};

export type EventDeliveryBroker = {
  state: string;
  generation?: string | number;
  active: number;
  active_capacity: number;
  terminal: number;
  terminal_capacity: number;
  terminal_content_bytes: number;
  terminal_content_bytes_capacity: number;
  bridges: EventDeliveryBridge[];
};

export type EventDeliveryRecord = {
  id: string;
  topic: string;
  source: string;
  ordering_key?: string;
  status: string;
  target_count?: number;
  failed_count?: number;
  failure_code?: string;
  observed_at?: string;
  terminal_at?: string;
};

export type EventDeliveryTransition = {
  at: string;
  phase: string;
  state: string;
  target?: string;
  code?: string;
};

export type EventDeliveryAttempt = {
  id?: string;
  target: string;
  state: string;
  attempt?: number;
  failure_code?: string;
  updated_at?: string;
};

export type EventDeliveryDetail = EventDeliveryRecord & {
  deliveries: EventDeliveryAttempt[];
  timeline: EventDeliveryTransition[];
};

export type EventDeliveryPage = {
  broker: EventDeliveryBroker;
  items: EventDeliveryRecord[];
  next_cursor: string | null;
};

export type LyfDiagnostic = {
  code: string;
  severity: string;
  message: string;
  source: string;
  span: JsonObject | null;
};

export type LyfResource = {
  path: string;
  source: string;
  diagnostics: LyfDiagnostic[];
};

export type LyfResourcePage = {
  read_only: boolean;
  grammar: string;
  items: LyfResource[];
};
export type WebUiLogRecord = { id: string; at: string; level: string; component: string; message: string; context: JsonObject };
export type WebUiLogsPage = { items: WebUiLogRecord[]; next_cursor: string | null; total_retained: number; diagnostics: string[] };
export type EventSummary = { window: { from: string | null; to: string | null }; totals: Record<string, number>; series: Json[]; breakdown: Array<{ key: string; value: number }> };
export type TopologyGraph = { generation: number; updated_at: string | null; nodes: Array<{ id: string; kind: string; label: string; state: string; metadata: JsonObject }>; edges: Array<{ id: string; source: string; target: string; kind: string; state: string; metadata: JsonObject }>; diagnostics: string[] };
export type WebUiLayout = "sidebar" | "inline" | "main-sidebar";
export type WebUiPreferences = { plugin_layout: WebUiLayout; followed?: string[]; toast_duration?: number; plugin_sources?: string[]; disabled_plugin_sources?: string[] };

export type PluginSource = {
  id: string;
  priority: number;
  official: boolean;
  url: string;
  cache_state: "cached" | "uncached";
  digest: string | null;
};

export type PluginBundleMetadata = {
  bundle_id: string;
  version: string;
  display_name: string;
  summary: string;
  publisher: { id: string; name: string; url: string } | null;
  license: { expression: string; url?: string } | null;
  status: "active" | "yanked";
  yanked_reason: string | null;
  runtime_kinds: string[];
  requested_capabilities: string[];
  dependencies: string[];
  repository: string | null;
  homepage: string | null;
  project_id: string;
  description: string;
  tags: string[];
  compatibility: string[];
  gallery: string[];
  changelog: string[];
  download_bytes: number | null;
  download_bytes_exact: boolean;
};

export type PluginDiscoveryRecord = PluginBundleMetadata & {
  source: string;
  source_priority: number;
  official: boolean;
  index_digest: string;
};

export type PluginDiscoveryPage = {
  query: string;
  filters: { source_id: string | null; runtime_kind: string | null; status: string };
  sources: PluginSource[];
  items: PluginDiscoveryRecord[];
  next_cursor: string | null;
  total: number;
  diagnostics: { source_id: string; code: string }[];
};

export type PluginGeneration = {
  id: string;
  runtime_id: string;
  runtime_kind: string;
  created_at: string;
  bundles: string[];
  roots: string[];
  disabled_roots: string[];
  enabled_bundle_set: string[];
  source_id: string | null;
  index_digest: string | null;
};

export type PluginTarget = {
  id: string;
  kind: string;
  target_type: "runtime" | "bridge";
  state: string;
  support_grade: string;
  active_generation: PluginGeneration | null;
  previous_generation: PluginGeneration | null;
  enabled_bundle_set: string[];
  restart_required: boolean;
};

export type PluginTargetPage = {
  items: PluginTarget[];
  limit: number;
};

export type PluginPreview = {
  source: PluginSource;
  index_digest: string;
  selected_target: { id: string; kind: string; support_grade: string };
  bundle: PluginBundleMetadata;
  resolved_closure: PluginBundleMetadata[];
  requested_capabilities: string[];
  download_bytes: number | null;
  download_bytes_exact: boolean;
  security: {
    execution_boundary: string;
    artifact_bytes_exposed: boolean;
    load_plan_exposed: boolean;
    credentials_exposed: boolean;
  };
};
export type PluginDetails = { project_id: string; selected: PluginBundleMetadata; versions: PluginBundleMetadata[] };
