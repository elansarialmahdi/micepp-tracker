import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { AICategorizationReview } from "./AICategorizationReview";

const mocks = vi.hoisted(() => ({
  previewServiceCategorization: vi.fn(),
  confirmServiceCategorization: vi.fn(),
}));

vi.mock("../../api/inventory", () => mocks);

test("regroupe la confirmation par catégorie et laisse les groupes décochés sans catégorie", async () => {
  mocks.previewServiceCategorization.mockResolvedValue({
    items: [
      {
        key: "react",
        category_name: "Frameworks et bibliothèques",
        existing_category_id: null,
        confidence: 0.9,
        reason: "Framework frontend",
      },
      {
        key: "axios",
        category_name: "Frameworks et bibliothèques",
        existing_category_id: null,
        confidence: 0.9,
        reason: "Bibliothèque HTTP",
      },
      {
        key: "postgres",
        category_name: "Données et stockage",
        existing_category_id: null,
        confidence: 0.9,
        reason: "Base de données",
      },
    ],
  });
  mocks.confirmServiceCategorization.mockResolvedValue({
    items: [
      {
        key: "postgres",
        category: {
          id: "category-data",
          name: "Données et stockage",
          description: null,
          created_at: "2026-07-15T12:00:00Z",
          updated_at: "2026-07-15T12:00:00Z",
          archived_at: null,
        },
      },
    ],
  });
  const onConfirmed = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(
    <QueryClientProvider client={client}>
      <AICategorizationReview
        platformId="platform-1"
        items={[
          { key: "react", name: "React" },
          { key: "axios", name: "Axios" },
          { key: "postgres", name: "PostgreSQL" },
        ]}
        onConfirmed={onConfirmed}
      />
    </QueryClientProvider>,
  );

  fireEvent.click(screen.getByRole("button", { name: "Catégorisation par IA" }));
  expect(await screen.findByDisplayValue("Frameworks et bibliothèques")).toBeInTheDocument();
  expect(screen.getAllByRole("checkbox")).toHaveLength(2);
  expect(screen.queryByText("React")).not.toBeInTheDocument();
  expect(screen.queryByText("Axios")).not.toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Conserver la catégorie Frameworks et bibliothèques",
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Confirmer la sélection" }));

  await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1));
  expect(mocks.confirmServiceCategorization).toHaveBeenCalledWith(
    "platform-1",
    expect.arrayContaining([
      expect.objectContaining({ key: "react", selected: false }),
      expect.objectContaining({ key: "axios", selected: false }),
      expect.objectContaining({ key: "postgres", selected: true }),
    ]),
  );
  expect(onConfirmed).toHaveBeenCalledWith([
    { key: "react", category: null },
    { key: "axios", category: null },
    {
      key: "postgres",
      category: expect.objectContaining({ name: "Données et stockage" }),
    },
  ]);
});
