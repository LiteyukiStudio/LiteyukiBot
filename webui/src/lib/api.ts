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

export class WebUiApi {
  private csrfToken: string | null = null;
  private initialization: Promise<void> | null = null;

  async initialize(): Promise<void> {
    if (this.initialization === null) {
      this.initialization = this.initializeSession().catch((error: unknown) => {
        this.initialization = null;
        throw error;
      });
    }
    return this.initialization;
  }

  private async initializeSession(): Promise<void> {
    const match = /^#ticket=([^&]+)$/.exec(window.location.hash);
    const result = match
      ? await this.request<{ csrf_token: string }>("/session", {
        method: "POST",
        body: JSON.stringify({ ticket: decodeURIComponent(match[1]) }),
      })
      : await this.request<{ csrf_token: string }>("/session");
    if (match) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/overview`);
    this.csrfToken = result.csrf_token;
  }

  bootstrap() { return this.request<JsonObject>("/bootstrap"); }
  presentation(locale: string) { return this.request<WebUiPresentation>(`/presentation?locale=${encodeURIComponent(locale)}`); }
  snapshot() { return this.request<JsonObject>("/snapshot"); }
  catalog() { return this.request<{ operations: WebUiOperation[] }>("/operations/catalog"); }
  ledger() { return this.request<{ items: JsonObject[] }>("/ledger?limit=100"); }
  audit() { return this.request<{ items: WebUiOperationRecord[] }>("/audit?limit=100"); }
  pluginSurfaces() { return this.request<JsonObject>("/plugins/surfaces"); }

  async submit(operation: WebUiOperation, target: string, input: JsonObject, confirmed: boolean) {
    return this.request<WebUiOperationRecord>("/operations", {
      method: "POST",
      headers: this.csrfToken ? { "x-csrf-token": this.csrfToken } : {},
      body: JSON.stringify({
        operation_id: operation.id,
        target,
        input,
        idempotency_key: crypto.randomUUID(),
        confirmed,
        confirmation_target: operation.confirmation === "target" ? target : null,
      }),
    });
  }

  events(onEvent: (type: string, data: JsonObject) => void, onError: () => void): EventSource {
    const source = new EventSource("/api/v1/events", { withCredentials: true });
    for (const type of ["snapshot", "ledger_append", "operation", "heartbeat", "reset"]) {
      source.addEventListener(type, (event) => {
        try { onEvent(type, JSON.parse((event as MessageEvent<string>).data) as JsonObject); } catch { onError(); }
      });
    }
    source.onerror = onError;
    return source;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`/api/v1${path}`, {
      ...init,
      credentials: "same-origin",
      headers: { "content-type": "application/json", ...init.headers },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { error?: { code?: string } } | null;
      throw new Error(body?.error?.code ?? `webui.request_failed.${response.status}`);
    }
    return response.json() as Promise<T>;
  }
}
