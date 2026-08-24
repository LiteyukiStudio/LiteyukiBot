import { expect, test, type Page } from "@playwright/test";

const bootstrap = {
  instance: "control-test",
  first_run: false,
  snapshot: {
    status: { state: "ready", version: "7.0.0b4" },
    topology: {
      kernel: { state: "ready", version: "7.0.0b4" },
      runtimes: [{ id: "onebot-primary", kind: "onebot", health: { state: "ready", protocol_version: "3", last_heartbeat: "now" } }],
      plugins: [{ id: "profile", name: "Profile", version: "0.4.0", state: "started", provides: ["profile.service:1"] }],
    },
  },
};

const topologyGraph = {
  generation: 7,
  updated_at: "2026-08-15T03:00:00Z",
  nodes: [
    { id: "kernel", kind: "kernel", label: "Liteyuki kernel", state: "ready", metadata: {} },
    { id: "onebot-primary", kind: "runtime", label: "onebot-primary", state: "ready", metadata: {} },
  ],
  edges: [{ id: "kernel-onebot", source: "kernel", target: "onebot-primary", kind: "runtime", state: "ready", metadata: {} }],
  diagnostics: [],
};

const preferences = { plugin_layout: "inline", toast_duration: 3000, followed: [] };
const eventSummary = { window: { from: null, to: null }, totals: {}, series: [], breakdown: [] };

const catalog = { operations: [
  { id: "management.runtime.stop", input_schema: { type: "object", properties: { runtime_id: { type: "string", description: "Runtime identifier" } }, required: ["runtime_id"] }, impact: "high", confirmation: "target", target: "runtime_id", target_input_field: "runtime_id" },
  { id: "management.runtime.restart", input_schema: { type: "object", properties: { runtime_id: { type: "string" } }, required: ["runtime_id"] }, impact: "standard", confirmation: "explicit", target: "runtime_id", target_input_field: "runtime_id" },
  { id: "management.plugin.install", input_schema: { type: "object", properties: { runtime_id: { type: "string" }, bundle_id: { type: "string" }, source_id: { type: "string" }, expected_index_digest: { type: "string" } }, required: ["runtime_id", "bundle_id"] }, impact: "standard", confirmation: "explicit", target: "runtime_id", target_input_field: "runtime_id" },
  { id: "management.plugin.update", input_schema: { type: "object", properties: { runtime_id: { type: "string" } }, required: ["runtime_id"] }, impact: "standard", confirmation: "explicit", target: "runtime_id", target_input_field: "runtime_id" },
  { id: "management.plugin.rollback", input_schema: { type: "object", properties: { runtime_id: { type: "string" } }, required: ["runtime_id"] }, impact: "high", confirmation: "target", target: "runtime_id", target_input_field: "runtime_id" },
  { id: "management.plugin.enable", input_schema: { type: "object", properties: { runtime_id: { type: "string" }, bundle_id: { type: "string" } }, required: ["runtime_id", "bundle_id"] }, impact: "standard", confirmation: "explicit", target: "runtime_id", target_input_field: "runtime_id" },
  { id: "management.plugin.disable", input_schema: { type: "object", properties: { runtime_id: { type: "string" }, bundle_id: { type: "string" } }, required: ["runtime_id", "bundle_id"] }, impact: "standard", confirmation: "explicit", target: "runtime_id", target_input_field: "runtime_id" },
  { id: "management.plugin.uninstall", input_schema: { type: "object", properties: { runtime_id: { type: "string" }, bundle_id: { type: "string" } }, required: ["runtime_id", "bundle_id"] }, impact: "high", confirmation: "target", target: "runtime_id", target_input_field: "runtime_id" },
  { id: "management.plugin.gc", input_schema: { type: "object", properties: { runtime_id: { type: "string" } }, required: [] }, impact: "high", confirmation: "explicit", target: "kernel", target_input_field: null },
] };

const messages = {
  "webui.app.name": "Liteyuki",
  "webui.nav.overview": "Overview", "webui.nav.events": "Event deliveries", "webui.nav.topology": "Topology", "webui.nav.runtimes": "Runtimes", "webui.nav.plugins": "Plugins", "webui.nav.configuration": "Configuration",
  "webui.header.language": "Language", "webui.header.theme": "Theme", "webui.header.accent": "Accent color", "webui.header.open_navigation": "Open navigation", "webui.locale.en-US": "English", "webui.locale.zh-CN": "Simplified Chinese",
  "webui.theme.system": "System", "webui.theme.light": "Light", "webui.theme.dark": "Dark", "webui.theme.blue": "Blue", "webui.theme.lavender": "Lavender", "webui.theme.cyan": "Cyan",
  "webui.status.ready": "Ready", "webui.status.runtimes": "{active} / {total} runtimes", "webui.action.refresh": "Refresh",
  "webui.overview.healthy": "Healthy", "webui.overview.kernel": "Kernel {state}", "webui.overview.active_runtimes": "Active runtimes: {active} / {total}", "webui.overview.new_operation": "New operation",
  "webui.metric.active_runtimes": "Active runtimes", "webui.metric.configured": "{count} configured", "webui.metric.enabled_plugins": "Enabled plugins", "webui.metric.loaded_generations": "loaded generations", "webui.metric.operation_records": "Operation records", "webui.metric.retained_evidence": "retained evidence", "webui.metric.unresolved_faults": "Unresolved faults", "webui.metric.none_recorded": "none recorded", "webui.metric.requires_review": "requires review",
  "webui.ledger.title": "Operation ledger", "webui.ledger.operation": "Operation", "webui.ledger.state": "State", "webui.ledger.updated": "Updated", "webui.ledger.empty": "No retained operation records.", "webui.runtime.health": "Runtime health", "webui.runtime.empty": "No supervised runtimes.", "webui.audit.recent": "Recent evidence", "webui.audit.empty": "No retained audit records.",
  "webui.runtimes.title": "Supervised runtimes", "webui.runtimes.queue_action": "Queue action", "webui.runtimes.runtime": "Runtime", "webui.runtimes.protocol": "Protocol", "webui.runtimes.activity": "Activity", "webui.plugins.title": "Plugin generations", "webui.plugins.empty": "No plugins are active in this instance.",
  "webui.plugins.subtitle": "Review metadata and manage isolated runtime generations.", "webui.plugins.refresh": "Refresh indexes", "webui.plugins.views": "Plugin views", "webui.plugins.discover": "Discover", "webui.plugins.managed": "Managed", "webui.plugins.discover_description": "Search bounded sources, inspect trust metadata, and review an exact target before installation.", "webui.plugins.search": "Search", "webui.plugins.search_placeholder": "Search bundle, publisher, or summary", "webui.plugins.source": "Source", "webui.plugins.all_sources": "All sources", "webui.plugins.runtime": "Runtime kind", "webui.plugins.all_runtimes": "All runtimes", "webui.plugins.status": "Release status", "webui.plugins.active": "Active", "webui.plugins.all_statuses": "All statuses", "webui.plugins.yanked": "Yanked", "webui.plugins.target": "Target", "webui.plugins.select_target": "Select a target", "webui.plugins.sources": "Indexes", "webui.plugins.source_unavailable": "Source {source} could not be refreshed.", "webui.plugins.no_results": "No plugin releases match the selected filters.", "webui.plugins.more_results": "More results are available on the server.", "webui.plugins.no_summary": "No publisher summary.", "webui.plugins.unknown_publisher": "Publisher unavailable", "webui.plugins.unknown_license": "License unavailable", "webui.plugins.review_install": "Review install", "webui.plugins.preview_title": "Installation preview", "webui.plugins.preview_description": "Verify the target, source digest, closure, and security boundary before queueing installation.", "webui.plugins.preview_failed": "The installation preview could not be loaded.", "webui.plugins.install": "Queue installation", "webui.plugins.install_queued": "Installation queued", "webui.plugins.install_failed": "Installation could not be queued.", "webui.plugins.operation_missing": "This lifecycle operation is not available to the current session.", "webui.plugins.managed_description": "Inspect active and rollback generations, then queue lifecycle changes through the audit ledger.", "webui.plugins.grade.stable": "Stable", "webui.plugins.grade.experimental": "Experimental", "webui.plugins.grade.mixed": "Mixed", "webui.plugins.grade.available": "Available", "webui.plugins.grade.unavailable": "Unavailable", "webui.plugins.restart_required": "Restart required", "webui.plugins.active_generation": "Active generation", "webui.plugins.previous_generation": "Previous generation", "webui.plugins.lifecycle": "Lifecycle actions", "webui.plugins.lifecycle_description": "Actions remain target-bound and are revalidated by the daemon.", "webui.plugins.bundle": "Bundle", "webui.plugins.no_bundle": "No bundle selected", "webui.plugins.update": "Update", "webui.plugins.enable": "Enable", "webui.plugins.disable": "Disable", "webui.plugins.rollback": "Rollback", "webui.plugins.uninstall": "Uninstall", "webui.plugins.gc": "Collect", "webui.plugins.disabled": "disabled", "webui.plugins.legacy_generation": "Legacy generation without source digest", "webui.plugins.none": "None retained", "webui.plugins.no_targets": "No managed plugin targets are configured.", "webui.plugins.publisher": "Publisher", "webui.plugins.license": "License", "webui.plugins.download": "Download size", "webui.plugins.closure": "Resolved closure", "webui.plugins.capabilities": "Requested capabilities", "webui.plugins.preview_metadata_only": "Only metadata and the exact index digest are shown; artifact bytes stay on the daemon.", "webui.plugins.preview_execution": "Code will execute only inside target {target} after the daemon accepts the operation.", "webui.plugins.state.active": "Active", "webui.plugins.state.yanked": "Yanked", "webui.plugins.state.ready": "Ready", "webui.plugins.state.running": "Running", "webui.plugins.state.starting": "Starting", "webui.plugins.state.enabled": "Enabled", "webui.plugins.state.disabled": "Disabled", "webui.plugins.state.healthy": "Healthy", "webui.plugins.state.experimental": "Experimental", "webui.plugins.state.available": "Available", "webui.plugins.state.configured": "Configured", "webui.plugins.state.unavailable": "Unavailable", "webui.lyf.tokenizing": "Tokenizing selected resource", "webui.lyf.tokenized": "TextMate scopes ready", "webui.lyf.plain_fallback": "Plain-text fallback", "webui.lyf.tokenize_error": "TextMate tokenization failed",
  "webui.topology.kernel": "Kernel", "webui.topology.runtimes": "Runtimes", "webui.topology.plugins": "Plugins", "webui.topology.audit": "Audit", "webui.topology.records": "{count} records", "webui.state.retained": "retained", "webui.state.ready": "Ready", "webui.state.healthy": "Healthy", "webui.state.started": "Started",
  "webui.configuration.title": "Instance configuration", "webui.configuration.instance": "Instance", "webui.configuration.kernel": "Kernel", "webui.configuration.transport": "WebUI transport", "webui.configuration.loopback": "loopback only", "webui.configuration.owner": "Operation owner", "webui.configuration.daemon": "instance daemon",
  "webui.error.unavailable": "Local service unavailable", "webui.error.unavailable_detail": "The WebUI could not read the running daemon.", "webui.action.retry": "Retry", "webui.operation.queued": "Operation queued", "webui.operation.queued_failed": "Operation could not be queued", "webui.operation.description": "Operation input is schema-validated and recorded by the daemon before the worker can execute it.", "webui.operation.confirm_hint": "High-impact operations require the exact target confirmation.", "webui.operation.confirm_target": "Confirm target", "webui.operation.confirm_placeholder": "Type the exact target identifier", "webui.action.cancel": "Cancel", "webui.operation.queue": "Queue operation", "webui.operation.queueing": "Queueing", "webui.operation.enter": "Enter {field}",
  "webui.event_delivery.active": "Active deliveries", "webui.event_delivery.terminal": "Retained terminal", "webui.event_delivery.broker_state": "Broker state", "webui.event_delivery.bridges": "Bridge sessions", "webui.event_delivery.title": "Event deliveries", "webui.event_delivery.retention": "Only bounded, redacted diagnostic records are retained.", "webui.event_delivery.filter.state": "State", "webui.event_delivery.filter.topic": "Topic", "webui.event_delivery.filter.source": "Source", "webui.event_delivery.filter.target": "Target", "webui.event_delivery.filter.failure": "Failure", "webui.event_delivery.filter.any": "Any", "webui.event_delivery.filter.apply": "Filter", "webui.event_delivery.filter.clear": "Clear filters", "webui.event_delivery.error": "Event delivery diagnostics could not be read.", "webui.event_delivery.bridges_empty": "No bridge session is registered.", "webui.event_delivery.table.topic": "Topic", "webui.event_delivery.table.source": "Source", "webui.event_delivery.table.status": "Status", "webui.event_delivery.table.targets": "Targets", "webui.event_delivery.table.observed": "Observed", "webui.event_delivery.loading": "Loading event deliveries", "webui.event_delivery.empty": "No retained event deliveries match these filters.", "webui.event_delivery.next_page": "Next page", "webui.event_delivery.detail.title": "Event delivery detail", "webui.event_delivery.detail.redacted": "Redacted diagnostic record", "webui.event_delivery.detail.error": "The selected event delivery is unavailable.", "webui.event_delivery.detail.deliveries": "Deliveries", "webui.event_delivery.detail.deliveries_empty": "No delivery attempts were retained.", "webui.event_delivery.detail.timeline": "Timeline", "webui.event_delivery.detail.timeline_empty": "No diagnostic transitions were retained.",
};

const zhMessages = {
  ...messages,
  "webui.nav.overview": "概览", "webui.nav.events": "事件投递", "webui.nav.topology": "拓扑", "webui.nav.runtimes": "运行时", "webui.nav.plugins": "插件", "webui.nav.configuration": "配置",
  "webui.header.language": "语言", "webui.header.theme": "主题", "webui.header.accent": "强调色", "webui.header.open_navigation": "打开导航", "webui.locale.en-US": "英语", "webui.locale.zh-CN": "简体中文",
  "webui.theme.system": "跟随系统", "webui.theme.light": "浅色", "webui.theme.dark": "深色", "webui.theme.blue": "蓝色", "webui.theme.lavender": "薰衣草", "webui.theme.cyan": "青色",
  "webui.status.ready": "就绪", "webui.status.runtimes": "{active} / {total} 个运行时", "webui.action.refresh": "刷新",
  "webui.overview.healthy": "健康", "webui.overview.kernel": "内核 {state}", "webui.overview.active_runtimes": "活跃运行时：{active} / {total}", "webui.overview.new_operation": "新建操作",
  "webui.metric.active_runtimes": "活跃运行时", "webui.metric.configured": "已配置 {count} 个", "webui.metric.enabled_plugins": "已启用插件", "webui.metric.loaded_generations": "已加载代次", "webui.metric.operation_records": "操作记录", "webui.metric.retained_evidence": "已保留证据", "webui.metric.unresolved_faults": "未解决故障", "webui.metric.none_recorded": "无记录", "webui.metric.requires_review": "需要复核",
  "webui.ledger.title": "操作账本", "webui.ledger.operation": "操作", "webui.ledger.state": "状态", "webui.ledger.updated": "更新时间", "webui.ledger.empty": "没有保留的操作记录。", "webui.runtime.health": "运行时健康状态", "webui.runtime.empty": "没有受监管的运行时。", "webui.audit.recent": "最近证据", "webui.audit.empty": "没有保留的审计记录。",
  "webui.runtimes.title": "受监管的运行时", "webui.runtimes.queue_action": "加入操作队列", "webui.runtimes.runtime": "运行时", "webui.runtimes.protocol": "协议", "webui.runtimes.activity": "活动", "webui.plugins.title": "插件代次", "webui.plugins.empty": "此实例没有活动插件。",
  "webui.topology.kernel": "内核", "webui.topology.runtimes": "运行时", "webui.topology.plugins": "插件", "webui.topology.audit": "审计", "webui.topology.records": "{count} 条记录", "webui.state.retained": "已保留", "webui.state.ready": "就绪", "webui.state.healthy": "健康", "webui.state.started": "已启动",
  "webui.configuration.title": "实例配置", "webui.configuration.instance": "实例", "webui.configuration.kernel": "内核", "webui.configuration.transport": "WebUI 传输", "webui.configuration.loopback": "仅回环", "webui.configuration.owner": "操作所有者", "webui.configuration.daemon": "实例 daemon",
  "webui.error.unavailable": "本地服务不可用", "webui.error.unavailable_detail": "WebUI 无法读取正在运行的 daemon。", "webui.action.retry": "重试", "webui.operation.queued": "操作已加入队列", "webui.operation.queued_failed": "操作无法加入队列", "webui.operation.description": "daemon 执行前会校验操作输入并记录到本地账本。", "webui.operation.confirm_hint": "高影响操作需要准确确认目标。", "webui.operation.confirm_target": "确认目标", "webui.operation.confirm_placeholder": "输入准确的目标标识", "webui.action.cancel": "取消", "webui.operation.queue": "加入操作队列", "webui.operation.queueing": "正在加入队列", "webui.operation.enter": "输入{field}",
  "webui.event_delivery.active": "活动投递", "webui.event_delivery.terminal": "保留的终态记录", "webui.event_delivery.broker_state": "Broker 状态", "webui.event_delivery.bridges": "Bridge 会话", "webui.event_delivery.title": "事件投递", "webui.event_delivery.retention": "仅保留有界且已脱敏的诊断记录。", "webui.event_delivery.filter.state": "状态", "webui.event_delivery.filter.topic": "主题", "webui.event_delivery.filter.source": "来源", "webui.event_delivery.filter.target": "目标", "webui.event_delivery.filter.failure": "失败", "webui.event_delivery.filter.any": "任意", "webui.event_delivery.filter.apply": "筛选", "webui.event_delivery.filter.clear": "清除筛选", "webui.event_delivery.error": "无法读取事件投递诊断信息。", "webui.event_delivery.bridges_empty": "没有已注册的 bridge 会话。", "webui.event_delivery.table.topic": "主题", "webui.event_delivery.table.source": "来源", "webui.event_delivery.table.status": "状态", "webui.event_delivery.table.targets": "目标", "webui.event_delivery.table.observed": "观测时间", "webui.event_delivery.loading": "正在加载事件投递", "webui.event_delivery.empty": "没有符合筛选条件的保留事件投递。", "webui.event_delivery.next_page": "下一页", "webui.event_delivery.detail.title": "事件投递详情", "webui.event_delivery.detail.redacted": "已脱敏诊断记录", "webui.event_delivery.detail.error": "所选事件投递不可用。", "webui.event_delivery.detail.deliveries": "投递", "webui.event_delivery.detail.deliveries_empty": "没有保留的投递尝试。", "webui.event_delivery.detail.timeline": "时间线", "webui.event_delivery.detail.timeline_empty": "没有保留的诊断转换。",
};

const eventDeliveries = {
  broker: { state: "ready", generation: 7, active: 1, active_capacity: 32, terminal: 2, terminal_capacity: 128, bridges: [{ id: "nonebot", state: "connected", session_state: "ready" }] },
  items: [{ id: "delivery-1", topic: "message.created", source: "source:a1b2", status: "delivered", target_count: 1, failed_count: 0, observed_at: "2026-08-15T03:00:00Z" }],
  next_cursor: null,
};

const eventDeliveryDetail = {
  ...eventDeliveries.items[0],
  deliveries: [{ id: "attempt-1", target: "nonebot", state: "delivered", attempt: 1, updated_at: "2026-08-15T03:00:01Z" }],
  timeline: [{ at: "2026-08-15T03:00:00Z", phase: "admission", state: "admitted" }, { at: "2026-08-15T03:00:01Z", phase: "delivery", state: "delivered", target: "nonebot" }],
};

const pluginDiscovery = {
  query: "",
  filters: { source_id: null, runtime_kind: null, status: "active" },
  sources: [{ id: "official", priority: 0, official: true, url: "https://example.invalid/index.json", cache_state: "cached", digest: "a".repeat(64) }],
  items: [{ bundle_id: "example.echo", version: "1.2.0", display_name: "Example Echo", summary: "A test plugin", publisher: { id: "example", name: "Example Publisher", url: "https://example.invalid/publisher" }, license: { expression: "MIT" }, status: "active", yanked_reason: null, runtime_kinds: ["onebot"], requested_capabilities: ["runtime.events.receive"], dependencies: [], repository: "https://example.invalid/repository", homepage: null, download_bytes: 128, download_bytes_exact: true, source: "official", source_priority: 0, official: true, index_digest: "a".repeat(64) }],
  next_cursor: null,
  total: 1,
  diagnostics: [],
};

const pluginTargets = {
  items: [{ id: "onebot-primary", kind: "onebot", target_type: "bridge", state: "ready", support_grade: "stable", active_generation: null, previous_generation: null, enabled_bundle_set: [], restart_required: false }],
  limit: 1,
};

const pluginPreview = {
  source: pluginDiscovery.sources[0],
  index_digest: "a".repeat(64),
  selected_target: { id: "onebot-primary", kind: "onebot", support_grade: "stable" },
  bundle: pluginDiscovery.items[0],
  resolved_closure: [pluginDiscovery.items[0]],
  requested_capabilities: ["runtime.events.receive"],
  download_bytes: 128,
  download_bytes_exact: true,
  security: { execution_boundary: "selected_runtime", artifact_bytes_exposed: false, load_plan_exposed: false, credentials_exposed: false },
};

async function mockDaemon(page: Page, onSubmit?: (body: unknown) => void, ledgerItems?: unknown[]) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/session")) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ csrf_token: "csrf" }) });
    if (path.endsWith("/presentation")) {
      const locale = url.searchParams.get("locale") === "zh-CN" ? "zh-CN" : "en-US";
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ locale, locales: ["en-US", "zh-CN"], messages: locale === "zh-CN" ? zhMessages : messages, webui_version: "1.0.0" }) });
    }
    if (path.endsWith("/bootstrap") || path.endsWith("/snapshot")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(bootstrap) });
    if (path.endsWith("/topology/graph")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(topologyGraph) });
    if (path.endsWith("/preferences") || path.endsWith("/plugins/followed")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(preferences) });
    if (path.endsWith("/operations/catalog")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(catalog) });
    if (path.endsWith("/plugins/discovery")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(pluginDiscovery) });
    if (path.endsWith("/plugins/targets")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(pluginTargets) });
    if (path.endsWith("/plugins/preview/example.echo")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(pluginPreview) });
    if (path.endsWith("/ledger")) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: ledgerItems ?? [{ id: "op-1", at: "2026-08-15T03:00:00Z", title: "management.runtime.restart", source: "redacted", status: "healthy", detail: "ok" }] }) });
    if (path.endsWith("/audit")) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [] }) });
    if (path.endsWith("/events/summary")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(eventSummary) });
    if (path.endsWith("/event-deliveries/delivery-1")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(eventDeliveryDetail) });
    if (path.endsWith("/event-deliveries")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(eventDeliveries) });
    if (path.endsWith("/events")) return route.fulfill({ contentType: "text/event-stream", body: "event: heartbeat\ndata: {}\n\n" });
    if (path.endsWith("/operations") && route.request().method() === "POST") { onSubmit?.(route.request().postDataJSON()); return route.fulfill({ contentType: "application/json", body: JSON.stringify({ id: "op-2", state: "queued" }) }); }
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { code: "missing" } }) });
  });
}

for (const [name, viewport] of [["desktop", { width: 1440, height: 960 }], ["mobile", { width: 390, height: 844 }]] as const) {
  test(`${name} application shell consumes the daemon snapshot without overflow`, async ({ page }) => {
    await mockDaemon(page);
    await page.setViewportSize(viewport);
    await page.goto("/#/overview");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
    expect(await page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBeTruthy();
    if (name === "mobile") { await page.getByRole("button", { name: "Open navigation" }).click(); await expect(page.getByRole("button", { name: "Runtimes" }).last()).toBeVisible(); await expect(page.getByLabel("Navigation").getByText("v7.0.0b4+1.0.0")).toBeVisible(); }
    else {
      await expect(page.getByText("v7.0.0b4+1.0.0")).toBeVisible();
      await expect(page.locator(".webui-workbench")).toHaveCount(0);
      await expect(page.locator(".webui-workspace-base")).toBeVisible();
      await expect(page.locator(".webui-workspace-base")).toHaveCSS("box-shadow", "none");
      const sidebarBackground = await page.locator(".webui-sidebar").evaluate((element) => getComputedStyle(element).backgroundColor);
      await expect(page.locator(".webui-topbar")).toHaveCSS("background-color", sidebarBackground);
      const [topbar, workspace, title] = await Promise.all([page.locator(".webui-topbar").boundingBox(), page.locator(".webui-workspace-base").boundingBox(), page.getByRole("heading", { name: "Overview" }).boundingBox()]);
      expect(topbar).not.toBeNull();
      expect(workspace).not.toBeNull();
      expect(title).not.toBeNull();
      expect(Math.abs(title!.x - workspace!.x)).toBeLessThan(3);
      expect(title!.y).toBeGreaterThan(topbar!.y);
      expect(title!.y + title!.height).toBeLessThan(topbar!.y + topbar!.height);
      expect(title!.y + title!.height).toBeLessThan(workspace!.y);
    }
  });
}

test("workspaces project live ledger, topology, runtimes, and plugins", async ({ page }) => {
  await mockDaemon(page);
  await page.goto("/#/events");
  await expect(page.getByRole("heading", { name: "Event deliveries" })).toBeVisible();
  await expect(page.getByText("message.created")).toBeVisible();
  await page.goto("/#/topology");
  await expect(page.getByText("onebot-primary")).toBeVisible();
  await page.goto("/#/plugins");
  await expect(page.getByRole("button", { name: "Discover" })).toBeVisible();
  await expect(page.getByText("Example Echo", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Managed" }).click();
  await expect(page.getByLabel("Target")).toHaveValue("onebot-primary");
});

test("ledger virtualizes large retained record lists", async ({ page }) => {
  const firstRecordAt = new Date("2026-08-15T03:00:00Z");
  const records = Array.from({ length: 300 }, (_, index) => ({ id: `op-${index}`, at: new Date(firstRecordAt.getTime() + index * 60_000).toISOString(), title: `operation-${index}`, source: "redacted", status: "healthy", detail: "ok" }));
  await mockDaemon(page, undefined, records);
  await page.goto("/#/overview");
  const viewport = page.locator('[data-slot="ledger-viewport"]');
  await expect(viewport).toBeVisible();
  await expect(page.getByText("operation-0")).toBeVisible();
  expect(await page.locator("tr[data-virtual-index]").count()).toBeLessThan(32);
  await viewport.evaluate((element) => { element.scrollTop = element.scrollHeight; element.dispatchEvent(new Event("scroll")); });
  await expect(page.getByText("operation-299")).toBeVisible();
});

test("event deliveries use redacted typed diagnostics and open a delivery timeline", async ({ page }) => {
  await mockDaemon(page);
  await page.goto("/#/events");
  await page.getByLabel("Topic").fill("message.created");
  await page.getByRole("button", { name: "Filter", exact: true }).click();
  await expect(page.getByText("source:a1b2")).toBeVisible();
  await page.getByText("message.created").first().click();
  await expect(page.getByRole("heading", { name: "Event delivery detail" })).toBeVisible();
  await expect(page.getByText("admission · admitted")).toBeVisible();
});

test("brand returns to overview only from another workspace", async ({ page }) => {
  await mockDaemon(page);
  await page.goto("/#/runtimes");
  const brand = page.getByRole("button", { name: "Liteyuki" });
  await brand.click();
  await expect(page).toHaveURL(/#\/overview$/);
  await brand.click();
  await expect(page).toHaveURL(/#\/overview$/);
});

test("handoff fragment redeems its ticket before loading the local snapshot", async ({ page }) => {
  const tickets: unknown[] = [];
  await mockDaemon(page);
  await page.route("**/api/v1/session", async (route) => { tickets.push(route.request().postDataJSON()); await route.fulfill({ contentType: "application/json", body: JSON.stringify({ csrf_token: "csrf" }) }); });
  await page.goto("/#ticket=one-time-ticket");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  expect(tickets).toEqual([{ ticket: "one-time-ticket" }]);
  await expect(page).toHaveURL(/#\/overview$/);
});

test("top bar persists the selected locale and applies the selected theme", async ({ page }) => {
  await mockDaemon(page);
  await page.goto("/#/overview");
  const language = page.getByRole("button", { name: "Language" });
  await language.click();
  await page.keyboard.press("Escape");
  await expect(language).toHaveCSS("box-shadow", "none");
  await language.click();
  await page.getByRole("menuitemradio", { name: "Simplified Chinese" }).click();
  await expect(page.getByRole("heading", { name: "概览" })).toBeVisible();
  await page.getByRole("button", { name: "主题" }).click();
  await page.getByRole("menuitemradio", { name: "薰衣草" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-accent", "lavender");
  await page.getByRole("button", { name: "主题" }).click();
  await page.getByRole("menuitemradio", { name: "深色" }).click();
  await expect(page.locator("html")).toHaveClass(/webui-theme-transition/);
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.locator(".webui-theme-reveal")).toHaveCount(0);
  await expect(page.locator("html")).not.toHaveClass(/webui-theme-transition/);
  await expect(page.getByRole("button", { name: "刷新" })).toBeVisible();
});

test("high-impact operations require an explicit target and submit typed input", async ({ page }) => {
  let submitted: unknown;
  await mockDaemon(page, (body) => { submitted = body; });
  await page.goto("/#/runtimes");
  await page.getByRole("button", { name: "Queue action" }).click();
  const submit = page.getByRole("button", { name: "Queue operation" });
  await expect(submit).toBeDisabled();
  await page.getByLabel(/runtime_id/).fill("onebot-primary");
  await page.getByLabel("Confirm target").fill("onebot-primary");
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect.poll(() => submitted).toMatchObject({ operation_id: "management.runtime.stop", target: "onebot-primary", input: { runtime_id: "onebot-primary" }, confirmed: true, confirmation_target: "onebot-primary" });
});

test("service errors render a recoverable unavailable state", async ({ page }) => {
  let sessionRequests = 0;
  await page.route("**/api/v1/**", (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/session")) sessionRequests += 1;
    return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "webui.bridge_unavailable" } }) });
  });
  await page.goto("/#/overview");
  await expect(page.getByText("Local service unavailable", { exact: true })).toBeVisible();
  const requestsBeforeRetry = sessionRequests;
  expect(requestsBeforeRetry).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Retry" }).click();
  await expect.poll(() => sessionRequests).toBe(requestsBeforeRetry + 1);
});
