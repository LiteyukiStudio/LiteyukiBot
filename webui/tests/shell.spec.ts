import { expect, test } from "@playwright/test";

for (const [name, viewport] of [
  ["desktop", { width: 1440, height: 960 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  test(`${name} shell stays within its viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Operational overview" })).toBeVisible();
    const fitsViewport = await page.locator("html").evaluate(
      (element) => element.scrollWidth <= element.clientWidth,
    );
    expect(fitsViewport).toBeTruthy();
  });
}

test("navigation and language controls update the visible workspace", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Events" }).click();
  await expect(page.getByRole("heading", { name: "Events" })).toBeVisible();
  await page.getByRole("button", { name: "Language" }).click();
  await expect(page.getByRole("heading", { name: "事件" })).toBeVisible();
});
