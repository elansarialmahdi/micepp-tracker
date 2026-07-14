import { expect, test } from "@playwright/test";

test("lance un scan mock et confirme les services détectés", async ({ page }) => {
  const user = { id: "user-e2e", username: "admin", display_name: "Administrateur", must_change_password: false, permissions: ["dashboard.read", "platform.scan"] };
  const job = {
    id: "scan-e2e", platform_id: "platform-e2e", target: "8.8.8.8", target_type: "ip", scan_type: "full",
    status: "succeeded", progress: 100, current_step: "résultats prêts", started_at: "2026-07-13T12:00:00Z",
    completed_at: "2026-07-13T12:00:01Z", error_code: null, sanitized_error: null, created_at: "2026-07-13T12:00:00Z",
    detections: [{ id: "detection-e2e", detected_name: "Nginx", detected_version: "1.26", detected_vendor: "nginx",
      detected_product: "nginx", detected_cpe: null, source_detector: "mock", confidence: 0.95, port: 80, protocol: "tcp",
      category_suggestion: "Web", category_confidence: 0.75, selected_for_import: true }],
  };
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ access_token: "token", token_type: "bearer", expires_in: 900, user }) }));
  await page.route("**/api/v1/platforms/platform-e2e", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ id: "platform-e2e", name: "Portail", normalized_target: "8.8.8.8", target_type: "ip" }) }));
  await page.route("**/api/v1/platforms/platform-e2e/scans", (route) => route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(job) }));
  await page.route("**/api/v1/scans/scan-e2e", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(job) }));
  await page.route("**/api/v1/scans/scan-e2e/confirm", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ created: 1, skipped: 0, categories_created: 1 }) }));

  await page.goto("/platforms/platform-e2e/scan");
  await page.getByLabel(/Je confirme être autorisé/).check();
  await page.getByRole("button", { name: "Lancer le scan" }).click();
  await expect(page.getByText("Services détectés")).toBeVisible();
  await page.getByLabel("Nom Nginx").fill("Nginx validé");
  await page.getByRole("button", { name: "Confirmer les services sélectionnés" }).click();
  await expect(page.getByText(/1 service.*ajouté/)).toBeVisible();
});
