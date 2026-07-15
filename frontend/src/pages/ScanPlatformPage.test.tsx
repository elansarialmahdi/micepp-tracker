import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, expect, test, vi } from "vitest";

import { ScanPlatformPage } from "./ScanPlatformPage";

const mocks = vi.hoisted(() => ({
  getPlatform: vi.fn(),
  launchScan: vi.fn(),
  getScan: vi.fn(),
  cancelScan: vi.fn(),
  confirmScan: vi.fn(),
  previewServiceCategorization: vi.fn(),
  confirmServiceCategorization: vi.fn(),
}));

vi.mock("../api/platforms", () => ({ getPlatform: mocks.getPlatform }));
vi.mock("../api/scans", () => ({
  launchScan: mocks.launchScan,
  getScan: mocks.getScan,
  cancelScan: mocks.cancelScan,
  confirmScan: mocks.confirmScan,
}));
vi.mock("../api/inventory", () => ({
  previewServiceCategorization: mocks.previewServiceCategorization,
  confirmServiceCategorization: mocks.confirmServiceCategorization,
}));
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

const job = {
  id: "scan-1",
  platform_id: "platform-1",
  target: "8.8.8.8",
  target_type: "ip",
  scan_type: "full",
  status: "succeeded",
  progress: 100,
  current_step: "résultats prêts",
  started_at: "2026-07-13T12:00:00Z",
  completed_at: "2026-07-13T12:00:01Z",
  error_code: null,
  sanitized_error: null,
  created_at: "2026-07-13T12:00:00Z",
  detections: [
    {
      id: "detection-1",
      detected_name: "Nginx",
      detected_version: "1.26",
      detected_vendor: "nginx",
      detected_product: "nginx",
      detected_cpe: null,
      source_detector: "mock-nmap,mock-web",
      confidence: 0.96,
      port: 80,
      protocol: "tcp",
      category_suggestion: "Web",
      category_confidence: 0.75,
      selected_for_import: true,
    },
  ],
};

beforeEach(() => {
  mocks.getPlatform.mockResolvedValue({
    id: "platform-1",
    name: "Portail",
    normalized_target: "8.8.8.8",
  });
  mocks.launchScan.mockResolvedValue(job);
  mocks.getScan.mockResolvedValue(job);
  mocks.confirmScan.mockResolvedValue({
    created: 1,
    skipped: 0,
    categories_created: 1,
  });
  mocks.previewServiceCategorization.mockResolvedValue({
    items: [
      {
        key: "detection-1",
        category_name: "Serveurs web",
        existing_category_id: "category-web",
        confidence: 0.98,
        reason: "Serveur HTTP",
      },
    ],
  });
  mocks.confirmServiceCategorization.mockResolvedValue({
    items: [{ key: "detection-1", category: { id: "category-web", name: "Serveurs web" } }],
  });
});

test("détecte automatiquement la cible puis permet de corriger et confirmer les détections", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/platforms/platform-1/scan"]}>
        <Routes>
          <Route
            path="/platforms/:platformId/scan"
            element={<ScanPlatformPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const launchButton = screen.getByRole("button", { name: "Lancer le scan" });
  expect(launchButton).toBeEnabled();
  fireEvent.click(launchButton);
  await waitFor(() =>
    expect(mocks.launchScan).toHaveBeenCalledWith("platform-1", {
      target: undefined,
      scan_type: "full",
    }),
  );
  expect(await screen.findByText("Services détectés")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Catégorisation par IA" }),
  );
  await waitFor(() => expect(mocks.previewServiceCategorization).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "Confirmer la sélection" }));
  await waitFor(() => expect(mocks.confirmServiceCategorization).toHaveBeenCalledOnce());
  expect(screen.getByLabelText("Catégorie Nginx")).toHaveValue("Serveurs web");
  fireEvent.change(screen.getByLabelText("Nom Nginx"), {
    target: { value: "Nginx corrigé" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Confirmer les services sélectionnés" }),
  );
  await waitFor(() =>
    expect(mocks.confirmScan.mock.calls[0]?.[1]?.[0]?.name).toBe(
      "Nginx corrigé",
    ),
  );
  expect(await screen.findByText(/1 service.*ajouté/)).toBeInTheDocument();
});
