import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { FoundationPage } from "./FoundationPage";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: "ok", service: "MICEPP-Tracker", version: "0.1.0" }),
    }),
  );
});

test("affiche la version retournée par l’API", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FoundationPage />
    </QueryClientProvider>,
  );

  expect(screen.getByRole("heading", { name: "MICEPP-Tracker" })).toBeInTheDocument();
  expect(await screen.findByText("API opérationnelle — version 0.1.0")).toBeInTheDocument();
});

