import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  History,
  LayoutDashboard,
  Power,
  Plus,
  Server,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { createPlatform, type PlatformInput } from "../api/platforms";
import { useAuth } from "../auth/AuthProvider";
import { ModalPortal } from "../components/ModalPortal";
import { PlatformForm } from "../features/platforms/PlatformForm";

const navigation = [
  {
    to: "/",
    label: "Tableau de bord",
    permission: "dashboard.read",
    icon: LayoutDashboard,
  },
  {
    to: "/platforms",
    label: "Plateformes",
    permission: "platform.read",
    icon: Server,
  },
  {
    to: "/activity",
    label: "Historique des activités",
    permission: "history.read",
    icon: History,
  },
  {
    to: "/users",
    label: "Utilisateurs et permissions",
    permission: "user.read",
    icon: Users,
  },
];

function CreatePlatformControl() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const creation = useMutation({ mutationFn: createPlatform });
  async function submitPlatform(input: PlatformInput) {
    const platform = await creation.mutateAsync(input);
    await queryClient.invalidateQueries({ queryKey: ["platforms"] });
    setCreating(false);
    navigate(`/platforms/${platform.id}`);
  }
  return (
    <>
      <div className="sidebar__create-group">
        <button
          className="sidebar__create"
          type="button"
          onClick={() => setCreating(true)}
        >
          Nouvelle Plateforme
        </button>
        <button
          className="sidebar__create-plus"
          type="button"
          onClick={() => setCreating(true)}
          aria-label="Ajouter une plateforme"
          data-tooltip="Ajouter une plateforme"
        >
          <Plus aria-hidden="true" />
        </button>
      </div>
      {creating && (
        <ModalPortal>
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                setCreating(false);
                creation.reset();
              }
            }}
          >
            <section
              className="settings-modal platform-create-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="create-platform-title"
            >
              <div className="section-header">
                <h2 id="create-platform-title">Nouvelle plateforme</h2>
                <button
                  type="button"
                  aria-label="Fermer"
                  data-tooltip="Fermer"
                  data-tooltip-placement="bottom"
                  onClick={() => {
                    setCreating(false);
                    creation.reset();
                  }}
                >
                  <X aria-hidden="true" />
                </button>
              </div>
              <PlatformForm
                submitLabel="Créer la plateforme"
                pending={creation.isPending}
                error={
                  creation.error instanceof ApiError
                    ? creation.error.message
                    : creation.error
                      ? "Le serveur est indisponible."
                      : null
                }
                onSubmit={submitPlatform}
                onCancel={() => {
                  setCreating(false);
                  creation.reset();
                }}
              />
            </section>
          </div>
        </ModalPortal>
      )}
    </>
  );
}

export function AppLayout() {
  const auth = useAuth();
  const role =
    auth.user?.roles?.join(", ") ||
    (auth.hasPermission("user.manage") ? "Administrateur" : "Utilisateur");

  return (
    <div className="dashboard-layout">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <span>MICEPP - TRACKER</span>
        </div>
        {auth.hasPermission("platform.create") && <CreatePlatformControl />}
        <nav className="sidebar__navigation" aria-label="Navigation principale">
          <ul className="sidebar__nav">
            {navigation
              .filter((item) => auth.hasPermission(item.permission))
              .map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.to}>
                    <NavLink to={item.to} end={item.to === "/"}>
                      <Icon aria-hidden="true" />
                      <span>{item.label}</span>
                    </NavLink>
                  </li>
                );
              })}
          </ul>
        </nav>
        <img className="sidebar__watermark" src="/assets/micepp-logo.png" alt="" aria-hidden="true" />
        <div className="sidebar__account">
          <span className="profile-avatar" aria-hidden="true">
            <UserRound />
          </span>
          <span className="sidebar__identity">
            <strong>{auth.user?.username}</strong>
            <small>{role}</small>
          </span>
          <button
            className="logout-button"
            type="button"
            onClick={() => void auth.logout()}
            aria-label="Se déconnecter"
            data-tooltip="Se déconnecter"
          >
            <Power aria-hidden="true" />
          </button>
        </div>
      </aside>
      <main className="dashboard-content">
        <Outlet />
      </main>
    </div>
  );
}
