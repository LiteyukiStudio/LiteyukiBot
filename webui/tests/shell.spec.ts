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

async function mockDaemon(page: Page, onSubmit?: (body: unknown) => void) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/session")) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ csrf_token: "csrf" }) });
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
  test(`${name} workbench consumes the daemon snapshot without overflow`, async ({ page }) => {
    await mockDaemon(page);
    await page.setViewportSize(viewport);
    await page.goto("/#/overview");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
    await expect(page.getByText("control-test")).toBeVisible();
    expect(await page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBeTruthy();
    if (name === "mobile") { await page.getByRole("button", { name: "Open navigation" }).click(); await expect(page.getByRole("button", { name: "Runtimes" }).last()).toBeVisible(); }
  });
}

test("workspaces project live ledger, topology, runtimes, and plugins", async ({ page }) => {
  await mockDaemon(page);
  await page.goto("/#/events");
  await expect(page.getByRole("heading", { name: "Ledger" })).toBeVisible();
  await expect(page.getByText("management.runtime.restart")).toBeVisible();
  await page.goto("/#/topology");
  await expect(page.getByText("onebot-primary")).toBeVisible();
  await page.goto("/#/plugins");
  await expect(page.getByText("Profile", { exact: true })).toBeVisible();
});

test("handoff fragment redeems its ticket before loading the local snapshot", async ({ page }) => {
  let ticket: unknown;
  await mockDaemon(page);
  await page.route("**/api/v1/session", async (route) => { ticket = route.request().postDataJSON(); await route.fulfill({ contentType: "application/json", body: JSON.stringify({ csrf_token: "csrf" }) }); });
  await page.goto("/#ticket=one-time-ticket");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  expect(ticket).toEqual({ ticket: "one-time-ticket" });
  await expect(page).toHaveURL(/#\/overview$/);
});

test("high-impact operations require an explicit target and submit typed input", async ({ page }) => {
  let submitted: unknown;
  await mockDaemon(page, (body) => { submitted = body; });
  await page.goto("/#/runtimes");
  await page.getByRole("button", { name: "Queue action" }).click();
  const submit = page.getByRole("button", { name: "Queue operation" });
  await expect(submit).toBeDisabled();
  await page.getByLabel(/runtime_id/).fill("onebot-primary");
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect.poll(() => submitted).toMatchObject({ operation_id: "management.runtime.stop", target: "onebot-primary", input: { runtime_id: "onebot-primary" }, confirmed: true, confirmation_target: "onebot-primary" });
});

test("service errors render a recoverable unavailable state", async ({ page }) => {
  await page.route("**/api/v1/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "webui.bridge_unavailable" } }) }));
  await page.goto("/#/overview");
  await expect(page.getByText("Local service unavailable", { exact: true })).toBeVisible();
});
