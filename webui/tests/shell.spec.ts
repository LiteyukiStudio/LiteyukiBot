import { expect, test } from "@playwright/test";

for (const [name, viewport] of [
  ["desktop", { width: 1440, height: 960 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  test(`${name} workbench stays within its viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/#/overview");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
    const fitsViewport = await page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth);
    expect(fitsViewport).toBeTruthy();
    if (name === "mobile") {
      const sidebarIsOffCanvas = await page.locator(".sidebar").evaluate((element) => element.getBoundingClientRect().right <= 0);
      expect(sidebarIsOffCanvas).toBeTruthy();
    }
  });
}

test("workspace routes and event details remain deep-linkable", async ({ page }) => {
  await page.goto("/#/events");
  await page.getByRole("button", { name: "Open Message event accepted" }).click();
  await expect(page.getByRole("complementary", { name: "Event detail" })).toBeVisible();
  await expect(page).toHaveURL(/#\/events\/evt_01J8A7H2$/);
  await page.getByRole("complementary", { name: "Event detail" }).getByLabel("Close detail").click();
  await expect(page).toHaveURL(/#\/events$/);
});

test("handoff fragment redeems its one-time local session ticket", async ({ page }) => {
  let requestBody: unknown;
  await page.route("**/api/v1/session", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ csrf_token: "test" }) });
  });
  await page.goto("/#ticket=one-time-ticket");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  expect(requestBody).toEqual({ ticket: "one-time-ticket" });
  await expect(page).toHaveURL(/#\/overview$/);
});

test("high impact operation requires target confirmation", async ({ page }) => {
  await page.goto("/#/runtimes/satori-edge");
  await page.getByRole("button", { name: "Runtime actions" }).click();
  await expect(page.getByRole("heading", { name: "Stop runtime" })).toBeVisible();
  const submit = page.getByRole("button", { name: "Queue operation" });
  await expect(submit).toBeDisabled();
  await page.getByPlaceholder("Enter the target identifier to continue.").fill("satori-edge");
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page.getByRole("heading", { name: "Operation queued" })).toBeVisible();
});

test("plugin contribution surface and language preference render through host UI", async ({ page }) => {
  await page.goto("/#/plugins");
  await expect(page.getByRole("heading", { name: "Profile activity" })).toBeVisible();
  await page.getByRole("button", { name: "Language" }).click();
  await expect(page.locator("h1")).toHaveText("插件");
  await expect(page.getByRole("heading", { name: "Profile activity" })).toBeVisible();
});

test("first-run route offers local bootstrap and returns to the workbench", async ({ page }) => {
  await page.goto("/?setup=1");
  await expect(page.getByRole("heading", { name: "Set up the local instance" })).toBeVisible();
  await page.getByRole("button", { name: "View empty workspace" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
});
