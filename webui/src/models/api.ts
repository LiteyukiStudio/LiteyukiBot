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
