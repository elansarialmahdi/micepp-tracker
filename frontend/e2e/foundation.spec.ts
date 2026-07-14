import { expect, test } from "@playwright/test";

test("connecte l’administrateur et impose le changement initial", async ({ page }) => {
  await page.route("**/api/v1/auth/refresh", async (route) => {
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "CSRF_VALIDATION_FAILED", message: "Session absente" } }),
    });
  });
  await page.route("**/api/v1/auth/login", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "test-access-token",
        token_type: "bearer",
        expires_in: 900,
        user: {
          id: "00000000-0000-0000-0000-000000000001",
          username: "admin",
          display_name: "Administrateur",
          must_change_password: true,
          permissions: ["dashboard.read"],
        },
      }),
    });
  });
  await page.goto("/");
  await page.getByLabel("Identifiant").fill("admin");
  await page.getByLabel("Mot de passe").fill("Initial!Password42");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("heading", { name: "Modifier le mot de passe initial" })).toBeVisible();
});

test("crée une plateforme sans cible depuis la grille", async ({ page }) => {
  let createdServices: Array<Record<string, unknown>> = [];
  const platform = {
    id: "platform-e2e",
    name: "Plateforme E2E",
    target_type: "none",
    target_value: null,
    normalized_target: null,
    description: null,
    created_by: "00000000-0000-0000-0000-000000000001",
    created_at: "2026-07-13T12:00:00Z",
    updated_at: "2026-07-13T12:00:00Z",
    last_inventory_scan_at: null,
    last_vulnerability_check_at: null,
    archived_at: null,
  };
  await page.route("**/api/v1/auth/refresh", (route) =>
    route.fulfill({ status: 403, contentType: "application/json", body: "{}" }),
  );
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "test-access-token",
        token_type: "bearer",
        expires_in: 900,
        user: {
          id: platform.created_by,
          username: "admin",
          display_name: "Administrateur",
          must_change_password: false,
          permissions: [
            "dashboard.read",
            "platform.read",
            "platform.create",
            "service.read",
            "service.create",
          ],
        },
      }),
    }),
  );
  await page.route("**/api/v1/platforms/platform-e2e", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(platform) }),
  );
  await page.route("**/api/v1/platforms/platform-e2e/categories", (route) =>
    route.fulfill({ contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/v1/platforms/platform-e2e/services/bulk", async (route) => {
    createdServices = [
      {
        id: "service-e2e",
        platform_id: "platform-e2e",
        category_id: null,
        category_name: null,
        name: "Apache",
        version: "2.4.62",
        source: "manual",
        archived_at: null,
      },
    ];
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(createdServices) });
  });
  await page.route("**/api/v1/platforms/platform-e2e/services?*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: createdServices, total: createdServices.length, page: 1, page_size: 25 }),
    }),
  );
  await page.route("**/api/v1/platforms?*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 12 }),
    }),
  );
  await page.route("**/api/v1/platforms", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(platform) });
    } else {
      await route.fallback();
    }
  });

  await page.goto("/");
  await page.getByLabel("Identifiant").fill("admin");
  await page.getByLabel("Mot de passe").fill("Initial!Password42");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.getByRole("link", { name: "Plateformes" }).click();
  await page.getByRole("link", { name: "Créer une plateforme" }).click();
  await page.getByLabel("Nom de la plateforme").fill("Plateforme E2E");
  await page.getByRole("button", { name: "Créer la plateforme" }).click();
  await expect(page.getByRole("heading", { name: "Plateforme E2E" })).toBeVisible();
  await page.getByRole("link", { name: "Ajouter des services" }).click();
  await page.getByLabel("Nom du service").fill("Apache");
  await page.getByLabel("Version (optionnelle)").fill("2.4.62");
  await page.getByRole("button", { name: "Confirmer l’ajout" }).click();
  await expect(page.getByRole("link", { name: "Apache" })).toBeVisible();
});
