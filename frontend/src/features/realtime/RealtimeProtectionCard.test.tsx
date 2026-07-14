import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { countdown, RealtimeProtectionCard } from "./RealtimeProtectionCard";

const mocks = vi.hoisted(() => ({
  getRealtimeSettings: vi.fn(),
  getCurrentProtectionJob: vi.fn(),
  runRealtimeProtection: vi.fn(),
  updateRealtimeSettings: vi.fn(),
}));

vi.mock("../../api/realtime", () => mocks);
vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

const baseSettings = {
  enabled: false,
  interval_seconds: 3600,
  batch_size: 25,
  max_concurrency: 2,
  min_interval_seconds: 60,
  last_run_at: null,
  next_run_at: null,
  updated_at: "2026-07-13T12:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getRealtimeSettings.mockResolvedValue(baseSettings);
  mocks.getCurrentProtectionJob.mockResolvedValue(null);
  mocks.runRealtimeProtection.mockResolvedValue({
    id: "job-1",
    status: "queued",
  });
  mocks.updateRealtimeSettings.mockResolvedValue(baseSettings);
});

afterEach(cleanup);

function renderCard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <RealtimeProtectionCard />
    </QueryClientProvider>,
  );
}

test("calcule un compte à rebours lisible depuis next_run_at", () => {
  expect(
    countdown("2026-07-13T13:02:03Z", Date.parse("2026-07-13T12:00:00Z")),
  ).toBe("1 h 2 min 3 s");
});

test("lance le pipeline manuel lorsque la protection est désactivée", async () => {
  renderCard();
  fireEvent.click(
    await screen.findByRole("button", { name: /vérifier maintenant/i }),
  );
  await waitFor(() =>
    expect(mocks.runRealtimeProtection).toHaveBeenCalledOnce(),
  );
});

test("configure l’intervalle lorsque la protection est activée", async () => {
  mocks.getRealtimeSettings.mockResolvedValue({
    ...baseSettings,
    enabled: true,
    next_run_at: "2099-01-01T00:00:00Z",
  });
  mocks.updateRealtimeSettings.mockResolvedValue({
    ...baseSettings,
    enabled: true,
    interval_seconds: 7200,
  });
  renderCard();
  fireEvent.click(await screen.findByRole("button", { name: /configurer/i }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Valeur"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  await waitFor(() =>
    expect(mocks.updateRealtimeSettings.mock.calls[0]?.[0]).toEqual({
      interval_seconds: 7200,
    }),
  );
});

test("cache complètement la vérification manuelle pendant un traitement", async () => {
  mocks.getCurrentProtectionJob.mockResolvedValue({
    id: "job-1",
    status: "running",
    total_services: 6,
    processed_services: 0,
    failed_services: 0,
    current_batch: 0,
    batch_size: 25,
    max_concurrency: 2,
    started_at: "2026-07-14T12:00:00Z",
  });
  renderCard();
  await screen.findByText(/vérification des services/i);
  expect(screen.getByText("0/6")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /vérifier maintenant/i }),
  ).not.toBeInTheDocument();
});
