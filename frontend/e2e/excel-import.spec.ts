import { expect, test } from "@playwright/test";

test("importe un fichier Excel après mapping et confirmation", async ({ page }) => {
  await page.route("**/api/v1/auth/refresh", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "test-access-token",
        token_type: "bearer",
        expires_in: 900,
        user: {
          id: "user-e2e",
          username: "admin",
          display_name: "Administrateur",
          must_change_password: false,
          permissions: ["dashboard.read", "service.import"],
        },
      }),
    }),
  );
  await page.route("**/api/v1/platforms/platform-e2e/service-imports", (route) =>
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        id: "import-e2e",
        filename: "services.xlsx",
        columns: [
          { index: 0, name: "Service" },
          { index: 1, name: "Version" },
        ],
        sample_rows: [["Nginx", "1.26"]],
        row_count: 1,
      }),
    }),
  );
  await page.route("**/api/v1/service-imports/import-e2e/preview", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "import-e2e",
        rows: [
          {
            row_number: 2,
            name: "Nginx",
            version: "1.26",
            category: null,
            status: "valid",
            duplicate_kind: null,
            errors: [],
          },
        ],
        valid_count: 1,
        invalid_count: 0,
        duplicate_count: 0,
      }),
    }),
  );
  await page.route("**/api/v1/service-imports/import-e2e/confirm", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        created: 1,
        merged: 0,
        skipped: 0,
        invalid: 0,
        categories_created: 0,
      }),
    }),
  );

  await page.goto("/platforms/platform-e2e/services/import");
  await page.getByLabel(/Fichier Excel/).setInputFiles({
    name: "services.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("mock-xlsx"),
  });
  await page.getByRole("button", { name: "Charger et analyser" }).click();
  await page.getByLabel(/Version/).selectOption("1");
  await page.getByRole("button", { name: "Valider le mapping" }).click();
  await expect(page.getByText("1 valide(s)")).toBeVisible();
  await page.getByRole("button", { name: "Confirmer l’import" }).click();
  await expect(page.getByRole("heading", { name: "Résumé de l’import" })).toBeVisible();
  await expect(page.getByText("Services créés").locator("..").getByText("1")).toBeVisible();
});
