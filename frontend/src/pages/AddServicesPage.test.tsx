import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, expect, test, vi } from "vitest";

import { AddServicesPage } from "./AddServicesPage";

const mocks = vi.hoisted(() => ({
  getCategories: vi.fn(),
  createServices: vi.fn(),
  createCategory: vi.fn(),
  previewServiceCategorization: vi.fn(),
  confirmServiceCategorization: vi.fn(),
}));

vi.mock("../api/inventory", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/inventory")>();
  return { ...original, ...mocks };
});

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

beforeEach(() => {
  mocks.getCategories.mockResolvedValue([
    { id: "category-web", name: "Serveurs web" },
    { id: "category-runtime", name: "Langages et runtimes" },
  ]);
  mocks.createServices.mockResolvedValue([]);
  mocks.createCategory.mockResolvedValue({});
  mocks.previewServiceCategorization.mockResolvedValue({
    items: [
      {
        key: "0",
        category_name: "Serveurs web",
        existing_category_id: "category-web",
        confidence: 0.98,
        reason: "Serveur HTTP",
      },
      {
        key: "1",
        category_name: "Langages et runtimes",
        existing_category_id: "category-runtime",
        confidence: 0.96,
        reason: "Runtime applicatif",
      },
    ],
  });
  mocks.confirmServiceCategorization.mockResolvedValue({
    items: [
      { key: "0", category: { id: "category-web", name: "Serveurs web" } },
      { key: "1", category: { id: "category-runtime", name: "Langages et runtimes" } },
    ],
  });
});

test("ajoute plusieurs lignes manuelles en une confirmation", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/platforms/platform-1/services/new"]}>
        <Routes>
          <Route
            path="/platforms/:platformId/services/new"
            element={<AddServicesPage />}
          />
          <Route
            path="/platforms/:platformId"
            element={<p>Retour plateforme</p>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  fireEvent.change(screen.getByLabelText("Nom du service"), {
    target: { value: "Apache" },
  });
  fireEvent.change(screen.getByLabelText("Version (optionnelle)"), {
    target: { value: "2.4.62" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ajouter une ligne" }));
  const names = screen.getAllByLabelText("Nom du service");
  fireEvent.change(names[1], { target: { value: "PHP" } });
  fireEvent.click(
    screen.getByRole("button", { name: "Catégorisation par IA" }),
  );
  await waitFor(() => expect(mocks.previewServiceCategorization).toHaveBeenCalledOnce());
  await waitFor(() => expect(mocks.confirmServiceCategorization).toHaveBeenCalledOnce());
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Confirmer l’ajout" }));

  await waitFor(() => {
    expect(mocks.createServices).toHaveBeenCalledWith("platform-1", [
      { name: "Apache", version: "2.4.62", category_id: "category-web" },
      { name: "PHP", version: null, category_id: "category-runtime" },
    ]);
  });
  expect(await screen.findByText("Retour plateforme")).toBeInTheDocument();
});
