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
