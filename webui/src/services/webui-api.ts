import type {
  EventDeliveryDetail,
  EventDeliveryFilters,
  EventDeliveryPage,
  LyfResourcePage,
  JsonObject,
  WebUiOperation,
  WebUiOperationRecord,
  WebUiPresentation,
} from "@/models/api";

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
      ? await this.request<{ csrf_token: string }>("/session", { method: "POST", body: JSON.stringify({ ticket: decodeURIComponent(match[1]) }) })
      : await this.request<{ csrf_token: string }>("/session");
    if (match) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/overview`);
    this.csrfToken = result.csrf_token;
  }

  bootstrap() { return this.request<JsonObject>("/bootstrap"); }
  presentation(locale: string) { return this.request<WebUiPresentation>(`/presentation?locale=${encodeURIComponent(locale)}`); }
  catalog() { return this.request<{ operations: WebUiOperation[] }>("/operations/catalog"); }
  ledger() { return this.request<{ items: JsonObject[] }>("/ledger?limit=100"); }
  audit() { return this.request<{ items: WebUiOperationRecord[] }>("/audit?limit=100"); }
  eventDeliveries(filters: EventDeliveryFilters = {}, cursor: string | null = null, limit = 100) {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    for (const [name, value] of Object.entries(filters)) if (value) query.set(name, value);
    return this.request<EventDeliveryPage>(`/event-deliveries?${query}`);
  }
  eventDelivery(eventId: string) { return this.request<EventDeliveryDetail>(`/event-deliveries/${encodeURIComponent(eventId)}`); }
  lyfResources() { return this.request<LyfResourcePage>("/lyf/resources"); }

  async submit(operation: WebUiOperation, target: string, input: JsonObject, confirmed: boolean) {
    return this.request<WebUiOperationRecord>("/operations", {
      method: "POST",
      headers: this.csrfToken ? { "x-csrf-token": this.csrfToken } : {},
      body: JSON.stringify({ operation_id: operation.id, target, input, idempotency_key: crypto.randomUUID(), confirmed, confirmation_target: operation.confirmation === "target" ? target : null }),
    });
  }

  events(onEvent: (type: string, data: JsonObject) => void, onError: () => void): EventSource {
    const source = new EventSource("/api/v1/events", { withCredentials: true });
    for (const type of ["snapshot", "ledger_append", "operation", "event_delivery", "heartbeat", "reset"]) {
      source.addEventListener(type, (event) => {
        try { onEvent(type, JSON.parse((event as MessageEvent<string>).data) as JsonObject); } catch { onError(); }
      });
    }
    source.onerror = onError;
    return source;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`/api/v1${path}`, { ...init, credentials: "same-origin", headers: { "content-type": "application/json", ...init.headers } });
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { error?: { code?: string } } | null;
      throw new Error(body?.error?.code ?? `webui.request_failed.${response.status}`);
    }
    return response.json() as Promise<T>;
  }
}
