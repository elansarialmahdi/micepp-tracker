import { expect, test } from "@playwright/test";

test("lance une vérification globale depuis la carte de protection", async ({ page }) => {
  const user = {
    id: "user-e2e",
    username: "admin",
    display_name: "Administrateur",
    must_change_password: false,
    permissions: ["dashboard.read", "settings.read", "settings.update"],
  };
  const settings = {
    enabled: false,
    interval_seconds: 3600,
    batch_size: 25,
    max_concurrency: 2,
    min_interval_seconds: 60,
    last_run_at: null,
    next_run_at: null,
    updated_at: "2026-07-13T12:00:00Z",
  };
  let currentJob: Record<string, unknown> | null = null;
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ access_token: "token", token_type: "bearer", expires_in: 900, user }),
  }));
  await page.route("**/api/v1/settings/realtime-protection", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(settings) });
  });
  await page.route("**/api/v1/settings/realtime-protection/current-job", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify(currentJob),
  }));
  await page.route("**/api/v1/settings/realtime-protection/run-now", (route) => {
    currentJob = {
      id: "job-e2e", trigger: "manual", status: "succeeded", total_services: 3,
      processed_services: 3, succeeded_services: 3, failed_services: 0,
      new_notifications: 1, current_batch: 1, retry_count: 0, error_summary: [],
      started_at: "2026-07-13T12:00:00Z", heartbeat_at: "2026-07-13T12:00:02Z",
      completed_at: "2026-07-13T12:00:03Z", created_at: "2026-07-13T12:00:00Z",
    };
    return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(currentJob) });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Protection en temps réel désactivée" })).toBeVisible();
  await page.getByRole("button", { name: "Vérifier maintenant" }).click();
  await expect(page.getByText(/3 réussi.*1 nouvelle/)).toBeVisible();
});
