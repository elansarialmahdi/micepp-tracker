import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, test, vi } from "vitest";

import { NotificationsPage } from "./NotificationsPage";

const mocks = vi.hoisted(() => ({
  getNotifications: vi.fn(),
  hideAllNotifications: vi.fn(),
  hideNotification: vi.fn(),
  readNotification: vi.fn(),
}));

vi.mock("../api/notifications", () => mocks);
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

beforeEach(() => {
  mocks.getNotifications.mockResolvedValue({
    items: [
      {
        id: "notification-1",
        type: "vulnerability.detected",
        title: "Vulnérabilité critique",
        message: "Une correction est requise.",
        severity: "critical",
        vulnerability_id: null,
        service_id: "service-1",
        service_name: "React",
        service_version: "18.2.0",
        threat_identifier: "CVE-2024-0001",
        platform_ids: ["platform-1"],
        platforms: [{ id: "platform-1", name: "Portail client" }],
        created_at: "2026-07-13T12:00:00Z",
        read_at: null,
        is_read: false,
        metadata: {},
      },
    ],
    total: 1,
    page: 1,
    page_size: 25,
  });
  mocks.readNotification.mockResolvedValue({});
  mocks.hideNotification.mockResolvedValue(undefined);
  mocks.hideAllNotifications.mockResolvedValue(undefined);
});

test("affiche la gravité textuellement et permet de masquer une notification", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText("Menace React 18.2.0")).toBeInTheDocument();
  expect(screen.getByText("Critique")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Voir les détails de la menace React 18.2.0" }),
  );
  expect(await screen.findByRole("dialog", { name: "Menace React 18.2.0" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Fermer" }));
  fireEvent.click(screen.getByRole("button", { name: "Masquer" }));
  await waitFor(() => expect(mocks.hideNotification.mock.calls[0]?.[0]).toBe("notification-1"));
});
