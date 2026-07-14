import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, test, vi } from "vitest";

import { PlatformsPage } from "./PlatformsPage";

const mocks = vi.hoisted(() => ({
  getPlatforms: vi.fn(),
  hasPermission: vi.fn(),
}));

vi.mock("../api/platforms", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/platforms")>();
  return { ...original, getPlatforms: mocks.getPlatforms };
});

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: mocks.hasPermission }),
}));

beforeEach(() => {
  mocks.getPlatforms.mockResolvedValue({
    items: [
      {
        id: "platform-1",
        name: "Portail MICEPP",
        target_type: "url",
        target_value: "https://micepp.example",
        normalized_target: "https://micepp.example/",
        description: "Portail institutionnel",
        created_by: "user-1",
        created_at: "2026-07-13T12:00:00Z",
        updated_at: "2026-07-13T12:00:00Z",
        last_inventory_scan_at: null,
        last_vulnerability_check_at: null,
        archived_at: null,
      },
    ],
    total: 1,
    page: 1,
    page_size: 12,
  });
  mocks.hasPermission.mockImplementation((permission: string) => permission === "platform.create");
});

test("affiche la grille et les filtres demandés", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/platforms?q=MICEPP"]}>
        <PlatformsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("link", { name: "Portail MICEPP" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Filtrer par" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Créer une plateforme" })).not.toBeInTheDocument();
  expect(mocks.getPlatforms).toHaveBeenCalledWith(
    expect.objectContaining({ page: 1, page_size: 100 }),
    expect.any(AbortSignal),
  );
});
