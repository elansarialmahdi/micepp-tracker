import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { PlatformForm } from "./PlatformForm";

test("adapte et valide la cible avant la création", async () => {
  const submit = vi.fn().mockResolvedValue(undefined);
  render(
    <PlatformForm
      submitLabel="Créer"
      pending={false}
      onSubmit={submit}
      onCancel={vi.fn()}
    />,
  );

  expect(screen.queryByLabelText("URL")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Nom de la plateforme"), {
    target: { value: "Portail public" },
  });
  fireEvent.click(screen.getByLabelText("Type de cible"));
  fireEvent.click(screen.getByRole("option", { name: "URL" }));
  fireEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByText("L’URL est obligatoire.")).toBeInTheDocument();
  expect(submit).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://example.com" } });
  fireEvent.click(screen.getByRole("button", { name: "Créer" }));
  await waitFor(() => {
    expect(submit).toHaveBeenCalledWith({
      name: "Portail public",
      target_type: "url",
      target_value: "https://example.com",
      description: null,
    });
  });
});
