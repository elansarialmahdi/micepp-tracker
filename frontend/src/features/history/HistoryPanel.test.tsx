import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { HistoryPanel } from "./HistoryPanel";

const mocks = vi.hoisted(() => ({
  getPlatformHistory: vi.fn(),
  hidePlatformHistory: vi.fn(),
}));

vi.mock("../../api/history", () => mocks);
vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

test("affiche et masque l’historique visible", async () => {
  mocks.getPlatformHistory.mockResolvedValue({
    items: [
      {
        id: "event-1",
        action: "service.create",
        actor_user_id: "user-1",
        summary: "Service créé : Nginx",
        created_at: "2026-07-13T12:00:00Z",
      },
    ],
    total: 1,
    page: 1,
    page_size: 25,
  });
  mocks.hidePlatformHistory.mockResolvedValue(undefined);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <HistoryPanel platformId="platform-1" />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("Service créé : Nginx")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Vider l’historique" }));
  await waitFor(() =>
    expect(mocks.hidePlatformHistory).toHaveBeenCalledWith("platform-1"),
  );

  expect(screen.getByRole("tooltip")).toHaveTextContent("Ancien historique");
  fireEvent.click(
    screen.getByRole("button", { name: "Voir l’ancien historique" }),
  );
  expect(
    await screen.findByRole("button", { name: "Retour" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Voir l’ancien historique" }),
  ).not.toBeInTheDocument();
});
