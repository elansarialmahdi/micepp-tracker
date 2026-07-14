import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, test, vi } from "vitest";

import { ServicesPanel } from "./ServicesPanel";

const mocks = vi.hoisted(() => ({
  getCategories: vi.fn(),
  getServices: vi.fn(),
}));

vi.mock("../../api/inventory", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/inventory")>();
  return { ...original, ...mocks };
});

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

beforeEach(() => {
  mocks.getCategories.mockResolvedValue([
    {
      id: "category-1",
      platform_id: "platform-1",
      name: "Web",
      description: null,
    },
  ]);
  mocks.getServices.mockResolvedValue({
    items: [
      {
        id: "service-1",
        platform_id: "platform-1",
        category_id: "category-1",
        category_name: "Web",
        name: "Apache",
        version: "2.4.62",
        source: "manual",
        archived_at: null,
      },
    ],
    total: 1,
    page: 1,
    page_size: 25,
  });
});

test("affiche les services avec un filtre unifié et sans colonne catégorie", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ServicesPanel platformId="platform-1" archived={false} />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(
    await screen.findByRole("link", { name: "Apache" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "2.4.62" })).toBeInTheDocument();
  expect(
    screen.queryByRole("columnheader", { name: "Catégorie" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Filtrer" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Filtrer" }));
  fireEvent.click(screen.getByRole("button", { name: "Catégorie" }));
  expect(screen.getByRole("menu", { name: "Catégorie" })).toBeInTheDocument();

  fireEvent.pointerDown(document.body);
  expect(
    screen.queryByRole("menu", { name: "Catégorie" }),
  ).not.toBeInTheDocument();
});
