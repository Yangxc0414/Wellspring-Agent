import { expect, test } from "@playwright/test";

test("live run exposes runtime loop, writing audit and evolution state", async ({ page }) => {
  const streamRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/events/stream")) streamRequests.push(request.url());
  });

  await page.goto("/");
  await page.getByRole("textbox", { name: "新会话输入" }).fill(
    "/live 钙钛矿界面钝化 湿热稳定性 浏览器 smoke"
  );
  await page.getByRole("button", { name: "开始新会话" }).click();

  await expect(page.locator(".task-head")).toContainText(
    /NEEDS HUMAN|COMPLETED|FAILED/,
    { timeout: 60_000 }
  );
  await expect(page.locator(".task-head")).toContainText("runtime ·");
  expect(streamRequests.length).toBeGreaterThan(0);

  await page.getByRole("tab", { name: "EVIDENCE" }).click();
  await expect(page.getByText("RESEARCH LOOP", { exact: true })).toBeVisible();
  await expect(page.getByText("NEXT ACTIONS", { exact: false })).toBeVisible();
  await expect(page.getByText("写作槽位", { exact: true })).toBeVisible();
  await expect(page.getByText("PROJECT EXPERIMENTS", { exact: true })).toBeVisible();
  await expect(page.getByText("EXP-BREAST-CANCER", { exact: false })).toBeVisible({ timeout: 15_000 });

  await page.getByRole("tab", { name: "PROJECTS" }).click();
  await expect(page.getByText("PROJECT EXPERIMENTS", { exact: true })).toBeVisible();
  await expect(page.getByText("EXP-BREAST-CANCER", { exact: false })).toBeVisible({ timeout: 15_000 });

  await page.getByRole("tab", { name: "EVOLUTION" }).click();
  await expect(page.getByText("RUNTIME EVOLUTION", { exact: true })).toBeVisible();
  await expect(page.getByText(/OBSERVATIONS \d+/)).toBeVisible();
});
