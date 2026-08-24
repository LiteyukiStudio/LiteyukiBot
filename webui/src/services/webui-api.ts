import type {
  EventDeliveryDetail,
  EventDeliveryFilters,
  EventDeliveryPage,
  LyfResourcePage,
  PluginDiscoveryPage,
  PluginPreview,
  PluginDetails,
  PluginTargetPage,
  JsonObject,
  WebUiOperation,
  WebUiOperationRecord,
  WebUiPresentation,
  EventSummary,
  TopologyGraph,
  WebUiLogsPage,
  WebUiPreferences,
} from "@/models/api";

/**
 * Owns the browser session and typed calls to the daemon's same-origin WebUI API.
 *
 * @remarks Mutating requests use the CSRF token issued during initialization. The class intentionally does not
 * persist that token outside memory; authenticated mode uses the daemon's HttpOnly session cookie,
 * while the development launcher may use its local development principal.
 */
export class WebUiApi {
  private csrfToken: string | null = null;
  private initialization: Promise<void> | null = null;

  /** Stable transport error that desktop hosts can map without parsing text. */
  static isObject(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }

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
  logs(filters: { cursor?: string; limit?: number; level?: string; component?: string; query?: string } = {}) {
    const query = new URLSearchParams({ limit: String(filters.limit ?? 100) });
    for (const [key, value] of Object.entries(filters)) if (value) query.set(key, String(value));
    return this.request<WebUiLogsPage>(`/logs?${query}`);
  }
  eventSummary(groupBy: "status" | "topic" = "status") { return this.request<EventSummary>(`/events/summary?group_by=${groupBy}`); }
  topologyGraph() { return this.request<TopologyGraph>("/topology/graph"); }
  preferences() { return this.request<WebUiPreferences>("/preferences"); }
  updatePreferences(value: WebUiPreferences) { return this.request<WebUiPreferences>("/preferences", { method: "PUT", headers: this.csrfToken ? { "x-csrf-token": this.csrfToken } : {}, body: JSON.stringify(value) }); }
  followedPlugins() { return this.request<WebUiPreferences>("/plugins/followed"); }
  updateFollowedPlugins(followed: string[]) { return this.request<WebUiPreferences>("/plugins/followed", { method: "PUT", headers: this.csrfToken ? { "x-csrf-token": this.csrfToken } : {}, body: JSON.stringify({ followed }) }); }

  /** @returns Read-only LYF resources and their parser diagnostics. */
  lyfResources() { return this.request<LyfResourcePage>("/lyf/resources"); }

  /**
   * @param filters - Server-side discovery filters and pagination state.
   * @returns Bounded plugin metadata; executable artifact bytes never cross this boundary.
   */
  pluginDiscovery(filters: {
    query?: string;
    sourceId?: string;
    runtimeKind?: string;
    status?: "active" | "yanked" | "all";
    refresh?: boolean;
    cursor?: string | null;
    limit?: number;
  } = {}) {
    const query = new URLSearchParams({ limit: String(filters.limit ?? 50) });
    if (filters.query) query.set("query", filters.query);
    if (filters.sourceId) query.set("source_id", filters.sourceId);
    if (filters.runtimeKind) query.set("runtime_kind", filters.runtimeKind);
    if (filters.status) query.set("status", filters.status);
    if (filters.refresh) query.set("refresh", "true");
    if (filters.cursor) query.set("cursor", filters.cursor);
    return this.request<PluginDiscoveryPage>(`/plugins/discovery?${query}`);
  }

  /** @returns Configured managed plugin targets and safe active/previous generation summaries. */
  pluginTargets() { return this.request<PluginTargetPage>("/plugins/targets"); }

  /** @returns One digest-bound, target-specific installation preview. */
  pluginPreview(bundleId: string, sourceId: string, targetId: string) {
    const query = new URLSearchParams({ source_id: sourceId, target_id: targetId });
    return this.request<PluginPreview>(`/plugins/preview/${encodeURIComponent(bundleId)}?${query}`);
  }
  pluginDetails(bundleId: string, sourceId: string) { return this.request<PluginDetails>(`/plugins/details/${encodeURIComponent(bundleId)}?source_id=${encodeURIComponent(sourceId)}`); }

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
        try {
          const value: unknown = JSON.parse((event as MessageEvent<string>).data);
          if (!WebUiApi.isObject(value)) throw new Error("webui.invalid_event_payload");
          onEvent(type, value as JsonObject);
        } catch { onError(); }
      });
    }
    source.onerror = onError;
    return source;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`/api/v1${path}`, { ...init, credentials: "same-origin", headers: { "content-type": "application/json", ...init.headers } });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      const error = WebUiApi.isObject(body) && WebUiApi.isObject(body.error) ? body.error : null;
      const code = error && typeof error.code === "string" ? error.code : `webui.request_failed.${response.status}`;
      throw new WebUiApiError(code, response.status, error && typeof error.message_key === "string" ? error.message_key : code);
    }
    const value: unknown = await response.json();
    if (!WebUiApi.isObject(value)) throw new WebUiApiError("webui.invalid_response", response.status, "webui.error.invalid_response");
    return value as T;
  }
}

export class WebUiApiError extends Error {
  constructor(public readonly code: string, public readonly status: number, public readonly messageKey = code) {
    super(code);
    this.name = "WebUiApiError";
  }
}
