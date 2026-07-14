import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, expect, test, vi } from "vitest";

import { ImportServicesPage } from "./ImportServicesPage";

const mocks = vi.hoisted(() => ({
  uploadServiceImport: vi.fn(),
  previewServiceImport: vi.fn(),
  confirmServiceImport: vi.fn(),
  previewServiceCategorization: vi.fn(),
  confirmServiceCategorization: vi.fn(),
}));

vi.mock("../api/imports", () => mocks);
vi.mock("../api/inventory", () => ({
  previewServiceCategorization: mocks.previewServiceCategorization,
  confirmServiceCategorization: mocks.confirmServiceCategorization,
}));
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

beforeEach(() => {
  mocks.uploadServiceImport.mockResolvedValue({
    id: "import-1",
    filename: "services.xlsx",
    columns: [
      { index: 0, name: "Service" },
      { index: 1, name: "Version" },
    ],
    sample_rows: [["Nginx", "1.26"]],
    row_count: 1,
  });
  mocks.previewServiceImport.mockResolvedValue({
    id: "import-1",
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
  });
  mocks.confirmServiceImport.mockResolvedValue({
    created: 1,
    merged: 0,
    skipped: 0,
    invalid: 0,
    categories_created: 0,
  });
  mocks.previewServiceCategorization.mockResolvedValue({
    items: [
      {
        key: "2",
        category_name: "Serveurs web",
        existing_category_id: null,
        confidence: 0.98,
        reason: "Serveur HTTP",
      },
    ],
  });
  mocks.confirmServiceCategorization.mockResolvedValue({
    items: [{ key: "2", category: { id: "category-web", name: "Serveurs web" } }],
  });
});

test("enchaîne upload, mapping, aperçu et confirmation", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/platforms/platform-1/services/import"]}>
        <Routes>
          <Route
            path="/platforms/:platformId/services/import"
            element={<ImportServicesPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const file = new File(["xlsx"], "services.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  fireEvent.change(screen.getByLabelText(/Fichier Excel/), {
    target: { files: [file] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Charger et analyser" }));
  expect(await screen.findByText(/1 ligne.*détectée/)).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText(/Version/));
  fireEvent.click(screen.getByRole("option", { name: "Version" }));
  fireEvent.click(screen.getByRole("button", { name: "Valider le mapping" }));
  expect(await screen.findByText("1 valide(s)")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Catégorisation par IA" }),
  );
  await waitFor(() => expect(mocks.previewServiceCategorization).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "Confirmer les catégories" }));
  await waitFor(() => expect(mocks.confirmServiceCategorization).toHaveBeenCalledOnce());
  expect(screen.getByLabelText("Catégorie de la ligne 2")).toHaveValue(
    "Serveurs web",
  );
  fireEvent.click(screen.getByRole("button", { name: "Confirmer l’import" }));
  expect(
    await screen.findByRole("heading", { name: "Résumé de l’import" }),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(mocks.confirmServiceImport.mock.calls[0]?.[0]).toBe("import-1"),
  );
  expect(mocks.confirmServiceImport.mock.calls[0]?.[3]).toEqual({
    2: "Serveurs web",
  });
});
