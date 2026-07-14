import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, expect, test, vi } from "vitest";

import { AppLayout } from "../layouts/AppLayout";
import { LoginPage } from "../pages/LoginPage";
import { ProtectedRoute } from "./ProtectedRoute";

const authMock = vi.hoisted(() => ({
  status: "anonymous" as "loading" | "authenticated" | "anonymous",
  user: null as null | {
    id: string;
    username: string;
    display_name: string;
    must_change_password: boolean;
    permissions: string[];
  },
  login: vi.fn(),
  logout: vi.fn(),
  changePassword: vi.fn(),
  hasPermission: vi.fn(),
}));

vi.mock("./AuthProvider", () => ({ useAuth: () => authMock }));

beforeEach(() => {
  authMock.status = "anonymous";
  authMock.user = null;
  authMock.login.mockReset();
  authMock.logout.mockReset();
  authMock.hasPermission.mockReset();
});

test("soumet le formulaire de connexion avec l’option de persistance", async () => {
  authMock.login.mockResolvedValue({ must_change_password: false });
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<p>Accueil privé</p>} />
      </Routes>
    </MemoryRouter>,
  );

  fireEvent.change(screen.getByLabelText("Identifiant"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("Mot de passe"), {
    target: { value: "Initial!Password42" },
  });
  fireEvent.click(screen.getByLabelText("Rester connecté"));
  fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));

  await waitFor(() => {
    expect(authMock.login).toHaveBeenCalledWith({
      username: "admin",
      password: "Initial!Password42",
      remember_me: true,
    });
  });
});

test("redirige une route privée vers la connexion", () => {
  render(
    <MemoryRouter initialEntries={["/private"]}>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/private" element={<p>Contenu privé</p>} />
        </Route>
        <Route path="/login" element={<p>Page de connexion</p>} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText("Page de connexion")).toBeInTheDocument();
  expect(screen.queryByText("Contenu privé")).not.toBeInTheDocument();
});

test("filtre la sidebar selon les permissions", () => {
  authMock.status = "authenticated";
  authMock.user = {
    id: "1",
    username: "reader",
    display_name: "Lecteur",
    must_change_password: false,
    permissions: ["dashboard.read"],
  };
  authMock.hasPermission.mockImplementation((permission: string) => permission === "dashboard.read");
  render(
    <MemoryRouter>
      <AppLayout />
    </MemoryRouter>,
  );
  expect(screen.getByRole("link", { name: "Tableau de bord" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Plateformes" })).not.toBeInTheDocument();
});

