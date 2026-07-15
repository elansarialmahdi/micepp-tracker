import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, test, vi } from "vitest";

import { NotificationsPanel } from "./NotificationsPanel";

const mocks = vi.hoisted(() => ({
  getNotifications: vi.fn(),
  hideAllNotifications: vi.fn(),
}));

vi.mock("../../api/notifications", () => mocks);
vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

const notification = {
  id: "notification-1",
  type: "vulnerability.detected",
  title: "CVE détectée",
  message: "Une vulnérabilité a été détectée.",
  severity: "medium" as const,
  vulnerability_id: null,
  service_id: "service-1",
  service_name: "React",
  service_version: "18.2.0",
  threat_identifier: "CVE-2024-0001",
  platform_ids: ["platform-1"],
  platforms: [{ id: "platform-1", name: "Portail client" }],
  created_at: "2026-07-15T12:00:00Z",
  read_at: null,
  is_read: false,
  metadata: {},
};

test("utilise le tooltip custom et affiche les anciennes notifications", async () => {
  mocks.getNotifications.mockImplementation(
    (_signal: AbortSignal | undefined, hidden: boolean) =>
      Promise.resolve({
        items: hidden
          ? [{ ...notification, id: "notification-2", title: "Ancienne CVE" }]
          : [notification],
        total: 1,
        page: 1,
        page_size: 25,
      }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NotificationsPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText("React 18.2.0")).toBeInTheDocument();
  const severity = screen.getByLabelText("Sévérité : Moyenne");
  expect(severity).toHaveAttribute("data-tooltip", "Sévérité : Moyenne");
  expect(severity).not.toHaveAttribute("title");

  fireEvent.click(
    screen.getByRole("button", { name: "Voir les détails de la menace React 18.2.0" }),
  );
  expect(await screen.findByRole("dialog", { name: "Menace React 18.2.0" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Portail client" })).toHaveAttribute(
    "href",
    "/platforms/platform-1",
  );
  fireEvent.click(screen.getByRole("button", { name: "Fermer" }));

  fireEvent.click(
    screen.getByRole("button", { name: "Voir les anciennes notifications" }),
  );
  expect(await screen.findByText("React 18.2.0")).toBeInTheDocument();
  expect(mocks.getNotifications).toHaveBeenLastCalledWith(
    expect.any(AbortSignal),
    true,
  );
});
