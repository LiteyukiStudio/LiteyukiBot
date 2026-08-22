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

/**
 * Owns the browser session and typed calls to the daemon's same-origin WebUI API.
 *
 * @remarks Mutating requests use the CSRF token issued during initialization. The class intentionally does not
 * persist that token outside memory; authentication remains the daemon's HttpOnly session cookie.
 */
export class WebUiApi {
  private csrfToken: string | null = null;
  private initialization: Promise<void> | null = null;

  /**
   * Establishes or reuses the browser session.
   * @returns A promise that resolves after a CSRF token is available.
   * @remarks Concurrent callers share one promise; a failed attempt is cleared so a later retry can recover.
   */
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

  /** @returns The daemon bootstrap projection used to construct the initial dashboard. */
  bootstrap() { return this.request<JsonObject>("/bootstrap"); }

  /**
   * @param locale - Preferred presentation locale.
   * @returns Localized labels and the supported locale catalog.
   */
  presentation(locale: string) { return this.request<WebUiPresentation>(`/presentation?locale=${encodeURIComponent(locale)}`); }

  /** @returns Operations the current local session is allowed to submit. */
  catalog() { return this.request<{ operations: WebUiOperation[] }>("/operations/catalog"); }

  /** @returns The most recent bounded operation-ledger page. */
  ledger() { return this.request<{ items: JsonObject[] }>("/ledger?limit=100"); }

  /** @returns The most recent redacted audit records. */
  audit() { return this.request<{ items: WebUiOperationRecord[] }>("/audit?limit=100"); }

  /**
   * Lists redacted broker delivery summaries.
   * @param filters - Exact diagnostic filters applied by the daemon.
   * @param cursor - Opaque cursor returned by a previous page, or `null` for the first page.
   * @param limit - Maximum records requested from the bounded ledger.
   * @returns One event-delivery page and its optional next cursor.
   */
  eventDeliveries(filters: EventDeliveryFilters = {}, cursor: string | null = null, limit = 100) {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    for (const [name, value] of Object.entries(filters)) if (value) query.set(name, value);
    return this.request<EventDeliveryPage>(`/event-deliveries?${query}`);
  }
  /**
   * @param eventId - Broker-issued event identifier from a delivery list row.
   * @returns Redacted delivery and transition details for the retained event.
   */
  eventDelivery(eventId: string) { return this.request<EventDeliveryDetail>(`/event-deliveries/${encodeURIComponent(eventId)}`); }

  /** @returns Read-only LYF resources and their parser diagnostics. */
  lyfResources() { return this.request<LyfResourcePage>("/lyf/resources"); }

  /**
   * Queues one catalog operation through the daemon's CSRF-protected control plane.
   * @param operation - Catalog contract selected by the user.
   * @param target - Explicit operation target and, where required, confirmation value.
   * @param input - JSON-safe input assembled from the operation schema.
   * @param confirmed - Whether the UI completed the operation's confirmation flow.
   * @returns The durable operation record created by the daemon.
   * @remarks The browser supplies an idempotency key, but the daemon remains responsible for authorization and
   * schema validation. This method is retained because the WebUI is an operator control surface.
   */
  async submit(operation: WebUiOperation, target: string, input: JsonObject, confirmed: boolean) {
    return this.request<WebUiOperationRecord>("/operations", {
      method: "POST",
      headers: this.csrfToken ? { "x-csrf-token": this.csrfToken } : {},
      body: JSON.stringify({ operation_id: operation.id, target, input, idempotency_key: crypto.randomUUID(), confirmed, confirmation_target: operation.confirmation === "target" ? target : null }),
    });
  }

  /**
   * Opens the same-origin server-sent event stream.
   * @param onEvent - Receives a validated event type and decoded JSON object.
   * @param onError - Receives transport failures and malformed event payloads.
   * @returns The open `EventSource`; the caller owns closing it.
   */
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
