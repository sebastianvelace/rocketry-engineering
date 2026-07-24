import { expect, test } from "@playwright/test";
import { mockGateway } from "./gateway-fixture";

const widths = [900, 1280, 1440];

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("rocketry-language", "es");
    localStorage.setItem("rocketry-view", "agent");
    localStorage.setItem("rocketry-rail-width", "72");
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockGateway(page);
});

for (const width of widths) {
  test(`agent workspace stays visually consistent at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Acceptance session" })).toBeVisible();
    await expect(page).toHaveScreenshot(`agent-${width}.png`, { maxDiffPixelRatio: 0.02 });
  });
}
