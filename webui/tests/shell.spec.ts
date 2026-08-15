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

const catalog = { operations: [
  { id: "management.runtime.stop", input_schema: { type: "object", properties: { runtime_id: { type: "string", description: "Runtime identifier" } }, required: ["runtime_id"] }, impact: "high", confirmation: "target", target: "runtime_id", target_input_field: "runtime_id" },
  { id: "management.runtime.restart", input_schema: { type: "object", properties: { runtime_id: { type: "string" } }, required: ["runtime_id"] }, impact: "standard", confirmation: "explicit", target: "runtime_id", target_input_field: "runtime_id" },
] };

const messages = {
  "webui.app.name": "Liteyuki",
  "webui.nav.overview": "Overview", "webui.nav.events": "Events", "webui.nav.topology": "Topology", "webui.nav.runtimes": "Runtimes", "webui.nav.plugins": "Plugins", "webui.nav.configuration": "Configuration",
  "webui.header.language": "Language", "webui.header.theme": "Theme", "webui.header.accent": "Accent color", "webui.header.open_navigation": "Open navigation",
  "webui.theme.system": "System", "webui.theme.light": "Light", "webui.theme.dark": "Dark", "webui.theme.blue": "Blue", "webui.theme.lavender": "Lavender", "webui.theme.cyan": "Cyan",
  "webui.status.ready": "Ready", "webui.status.runtimes": "{active} / {total} runtimes", "webui.action.refresh": "Refresh",
  "webui.overview.healthy": "Healthy", "webui.overview.kernel": "Kernel {state}", "webui.overview.active_runtimes": "Active runtimes: {active} / {total}", "webui.overview.new_operation": "New operation",
  "webui.metric.active_runtimes": "Active runtimes", "webui.metric.configured": "{count} configured", "webui.metric.enabled_plugins": "Enabled plugins", "webui.metric.loaded_generations": "loaded generations", "webui.metric.operation_records": "Operation records", "webui.metric.retained_evidence": "retained evidence", "webui.metric.unresolved_faults": "Unresolved faults", "webui.metric.none_recorded": "none recorded", "webui.metric.requires_review": "requires review",
  "webui.ledger.title": "Operation ledger", "webui.ledger.operation": "Operation", "webui.ledger.state": "State", "webui.ledger.updated": "Updated", "webui.ledger.empty": "No retained operation records.", "webui.runtime.health": "Runtime health", "webui.runtime.empty": "No supervised runtimes.", "webui.audit.recent": "Recent evidence", "webui.audit.empty": "No retained audit records.",
  "webui.runtimes.title": "Supervised runtimes", "webui.runtimes.queue_action": "Queue action", "webui.runtimes.runtime": "Runtime", "webui.runtimes.protocol": "Protocol", "webui.runtimes.activity": "Activity", "webui.plugins.title": "Plugin generations", "webui.plugins.empty": "No plugins are active in this instance.",
  "webui.topology.kernel": "Kernel", "webui.topology.runtimes": "Runtimes", "webui.topology.plugins": "Plugins", "webui.topology.audit": "Audit", "webui.topology.records": "{count} records", "webui.state.retained": "retained", "webui.state.ready": "Ready", "webui.state.healthy": "Healthy", "webui.state.started": "Started",
  "webui.configuration.title": "Instance configuration", "webui.configuration.instance": "Instance", "webui.configuration.kernel": "Kernel", "webui.configuration.transport": "WebUI transport", "webui.configuration.loopback": "loopback only", "webui.configuration.owner": "Operation owner", "webui.configuration.daemon": "instance daemon",
  "webui.error.unavailable": "Local service unavailable", "webui.error.unavailable_detail": "The WebUI could not read the running daemon.", "webui.action.retry": "Retry", "webui.operation.queued": "Operation queued", "webui.operation.queued_failed": "Operation could not be queued", "webui.operation.description": "Operation input is schema-validated and recorded by the daemon before the worker can execute it.", "webui.operation.confirm_hint": "High-impact operations require the exact target confirmation.", "webui.operation.confirm_target": "Confirm target", "webui.operation.confirm_placeholder": "Type the exact target identifier", "webui.action.cancel": "Cancel", "webui.operation.queue": "Queue operation", "webui.operation.queueing": "Queueing", "webui.operation.enter": "Enter {field}",
};

const zhMessages = {
  ...messages,
  "webui.nav.overview": "概览", "webui.nav.events": "事件", "webui.nav.topology": "拓扑", "webui.nav.runtimes": "运行时", "webui.nav.plugins": "插件", "webui.nav.configuration": "配置",
  "webui.header.language": "语言", "webui.header.theme": "主题", "webui.header.accent": "强调色", "webui.header.open_navigation": "打开导航",
  "webui.theme.system": "跟随系统", "webui.theme.light": "浅色", "webui.theme.dark": "深色", "webui.theme.blue": "蓝色", "webui.theme.lavender": "薰衣草", "webui.theme.cyan": "青色",
  "webui.status.ready": "就绪", "webui.status.runtimes": "{active} / {total} 个运行时", "webui.action.refresh": "刷新",
  "webui.overview.healthy": "健康", "webui.overview.kernel": "内核 {state}", "webui.overview.active_runtimes": "活跃运行时：{active} / {total}", "webui.overview.new_operation": "新建操作",
  "webui.metric.active_runtimes": "活跃运行时", "webui.metric.configured": "已配置 {count} 个", "webui.metric.enabled_plugins": "已启用插件", "webui.metric.loaded_generations": "已加载代次", "webui.metric.operation_records": "操作记录", "webui.metric.retained_evidence": "已保留证据", "webui.metric.unresolved_faults": "未解决故障", "webui.metric.none_recorded": "无记录", "webui.metric.requires_review": "需要复核",
  "webui.ledger.title": "操作账本", "webui.ledger.operation": "操作", "webui.ledger.state": "状态", "webui.ledger.updated": "更新时间", "webui.ledger.empty": "没有保留的操作记录。", "webui.runtime.health": "运行时健康状态", "webui.runtime.empty": "没有受监管的运行时。", "webui.audit.recent": "最近证据", "webui.audit.empty": "没有保留的审计记录。",
  "webui.runtimes.title": "受监管的运行时", "webui.runtimes.queue_action": "加入操作队列", "webui.runtimes.runtime": "运行时", "webui.runtimes.protocol": "协议", "webui.runtimes.activity": "活动", "webui.plugins.title": "插件代次", "webui.plugins.empty": "此实例没有活动插件。",
  "webui.topology.kernel": "内核", "webui.topology.runtimes": "运行时", "webui.topology.plugins": "插件", "webui.topology.audit": "审计", "webui.topology.records": "{count} 条记录", "webui.state.retained": "已保留", "webui.state.ready": "就绪", "webui.state.healthy": "健康", "webui.state.started": "已启动",
  "webui.configuration.title": "实例配置", "webui.configuration.instance": "实例", "webui.configuration.kernel": "内核", "webui.configuration.transport": "WebUI 传输", "webui.configuration.loopback": "仅回环", "webui.configuration.owner": "操作所有者", "webui.configuration.daemon": "实例 daemon",
  "webui.error.unavailable": "本地服务不可用", "webui.error.unavailable_detail": "WebUI 无法读取正在运行的 daemon。", "webui.action.retry": "重试", "webui.operation.queued": "操作已加入队列", "webui.operation.queued_failed": "操作无法加入队列", "webui.operation.description": "daemon 执行前会校验操作输入并记录到本地账本。", "webui.operation.confirm_hint": "高影响操作需要准确确认目标。", "webui.operation.confirm_target": "确认目标", "webui.operation.confirm_placeholder": "输入准确的目标标识", "webui.action.cancel": "取消", "webui.operation.queue": "加入操作队列", "webui.operation.queueing": "正在加入队列", "webui.operation.enter": "输入{field}",
};

async function mockDaemon(page: Page, onSubmit?: (body: unknown) => void) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/session")) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ csrf_token: "csrf" }) });
    if (path.endsWith("/presentation")) {
      const locale = url.searchParams.get("locale") === "zh-CN" ? "zh-CN" : "en-US";
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ locale, locales: ["en-US", "zh-CN"], messages: locale === "zh-CN" ? zhMessages : messages, webui_version: "1.0.0" }) });
    }
    if (path.endsWith("/bootstrap") || path.endsWith("/snapshot")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(bootstrap) });
    if (path.endsWith("/operations/catalog")) return route.fulfill({ contentType: "application/json", body: JSON.stringify(catalog) });
    if (path.endsWith("/ledger")) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [{ id: "op-1", at: "2026-08-15T03:00:00Z", title: "management.runtime.restart", source: "redacted", status: "healthy", detail: "ok" }] }) });
    if (path.endsWith("/audit")) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [] }) });
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
      const sidebarBackground = await page.locator(".webui-sidebar").evaluate((element) => getComputedStyle(element).backgroundColor);
      await expect(page.locator(".webui-topbar")).toHaveCSS("background-color", sidebarBackground);
    }
  });
}

test("workspaces project live ledger, topology, runtimes, and plugins", async ({ page }) => {
  await mockDaemon(page);
  await page.goto("/#/events");
  await expect(page.getByRole("heading", { name: "Events" })).toBeVisible();
  await expect(page.getByText("management.runtime.restart")).toBeVisible();
  await page.goto("/#/topology");
  await expect(page.getByText("onebot-primary")).toBeVisible();
  await page.goto("/#/plugins");
  await expect(page.getByText("Profile", { exact: true })).toBeVisible();
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
  await page.getByRole("button", { name: "Language" }).click();
  await page.getByRole("menuitemradio", { name: "简体中文" }).click();
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
