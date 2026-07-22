import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearActivityHistory, getActivityHistory } from "../api/history";
import { ActivityPage } from "./ActivityPage";

vi.mock("../api/history", async () => {
  const actual = await vi.importActual<typeof import("../api/history")>("../api/history");
  return { ...actual, clearActivityHistory: vi.fn(), getActivityHistory: vi.fn() };
});

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: (permission: string) => permission === "history.clear" }),
}));

describe("ActivityPage", () => {
  beforeEach(() => {
    vi.mocked(clearActivityHistory).mockResolvedValue(undefined);
    vi.mocked(getActivityHistory).mockResolvedValue({
      items: [
        {
          id: "event-1",
          actor_user_id: "user-1",
          actor_name: "Admin sécurité",
          action: "auth.login.failed",
          entity_type: "session",
          entity_id: null,
          platform_id: null,
          summary: "Échec de connexion pour admin",
          before_data: null,
          after_data: null,
          metadata: {
            result: "failure",
            browser: "Google Chrome 126.0.0.0",
            status_code: 401,
          },
          ip: "203.0.113.42",
          request_id: "request-1",
          created_at: "2026-07-20T12:30:00Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
      success_total: 8,
      failure_total: 1,
    });
  });

  it("affiche un journal détaillé et actualisé automatiquement", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ActivityPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Échec de connexion pour admin")).toBeInTheDocument();
    expect(screen.getByText("Admin sécurité")).toBeInTheDocument();
    expect(screen.getByText("203.0.113.42")).toBeInTheDocument();
    expect(screen.getByText("Google Chrome 126.0.0.0")).toBeInTheDocument();
    expect(screen.getByText(/Actualisation toutes les 5 secondes/)).toBeInTheDocument();
    unmount();
    queryClient.clear();
  });

  it("permet à l’administrateur d’effacer les logs après confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ActivityPage />
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Effacer les logs" }));
    await waitFor(() => expect(clearActivityHistory).toHaveBeenCalledTimes(1));
    unmount();
    queryClient.clear();
  });
});
