import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  FileSpreadsheet,
  FolderPlus,
  ListPlus,
  MoreHorizontal,
  Pencil,
  Plus,
  Radar,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";

import { ApiError } from "../api/client";
import {
  archivePlatform,
  getPlatform,
  updatePlatform,
  type PlatformInput,
} from "../api/platforms";
import { useAuth } from "../auth/AuthProvider";
import { ModalPortal } from "../components/ModalPortal";
import { HistoryPanel } from "../features/history/HistoryPanel";
import { PlatformForm } from "../features/platforms/PlatformForm";
import { ServicesPanel } from "../features/services/ServicesPanel";
import { AddServicesPage } from "./AddServicesPage";
import { ImportServicesPage } from "./ImportServicesPage";
import { ScanPlatformPage } from "./ScanPlatformPage";

type AddMethod = "choice" | "scan" | "import" | "manual";

const addMethodTitles: Record<AddMethod, string> = {
  choice: "Ajouter des services",
  scan: "Scanner et ajouter des services",
  import: "Importer des services depuis Excel",
  manual: "Ajouter des services manuellement",
};

export function PlatformDetailPage() {
  const { platformId = "" } = useParams();
  const auth = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [addingServices, setAddingServices] = useState(false);
  const [categoriesOpen, setCategoriesOpen] = useState(false);
  const [addMethod, setAddMethod] = useState<AddMethod>("choice");

  useEffect(() => {
    if (!menuOpen) return;
    const closeMenu = (event: PointerEvent) => {
      if (!(event.target as Element).closest(".action-menu"))
        setMenuOpen(false);
    };
    document.addEventListener("pointerdown", closeMenu);
    return () => document.removeEventListener("pointerdown", closeMenu);
  }, [menuOpen]);

  const closeAddServices = () => {
    setAddingServices(false);
    setAddMethod("choice");
  };
  const platform = useQuery({
    queryKey: ["platform", platformId],
    queryFn: ({ signal }) => getPlatform(platformId, signal),
    enabled: Boolean(platformId),
  });
  const update = useMutation({
    mutationFn: (input: PlatformInput) => updatePlatform(platformId, input),
  });
  const archive = useMutation({
    mutationFn: () => archivePlatform(platformId),
  });

  async function submit(input: PlatformInput) {
    const updated = await update.mutateAsync(input);
    queryClient.setQueryData(["platform", platformId], updated);
    await queryClient.invalidateQueries({ queryKey: ["platforms"] });
    setEditing(false);
  }

  async function archiveCurrent() {
    if (
      !window.confirm(
        "Supprimer cette plateforme de l’affichage ? Ses données et son historique seront conservés.",
      )
    )
      return;
    await archive.mutateAsync();
    await queryClient.invalidateQueries({ queryKey: ["platforms"] });
    navigate("/platforms");
  }

  if (platform.isPending)
    return <p role="status">Chargement de la plateforme…</p>;
  if (platform.isError || !platform.data)
    return (
      <div className="form-error" role="alert">
        {platform.error instanceof ApiError
          ? platform.error.message
          : "Impossible de charger la plateforme."}
      </div>
    );

  return (
    <section className="platform-detail-page" aria-labelledby="platform-title">
      <div className="page-header platform-detail-header">
        <div className="page-title-block">
          <h1 id="platform-title">{platform.data.name}</h1>
          <p>{platform.data.normalized_target ?? "Aucune URL ou adresse IP"}</p>
        </div>
        {!platform.data.archived_at && (
          <div className="platform-header-actions">
            {auth.hasPermission("service.create") && (
              <button
                className="primary-button"
                type="button"
                onClick={() => setAddingServices(true)}
              >
                <Plus aria-hidden="true" />
                Ajouter des services
              </button>
            )}
            {auth.hasPermission("service.create") && (
              <button
                className="secondary-button"
                type="button"
                onClick={() => setCategoriesOpen((current) => !current)}
                aria-pressed={categoriesOpen}
                aria-expanded={categoriesOpen}
                aria-haspopup="dialog"
              >
                <FolderPlus aria-hidden="true" />
                Catégories
              </button>
            )}
            <div className="action-menu">
              <button
                type="button"
                aria-label="Actions de la plateforme"
                data-tooltip="Actions de la plateforme"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((value) => !value)}
              >
                <MoreHorizontal aria-hidden="true" />
              </button>
              {menuOpen && (
                <div className="action-menu__content">
                  {auth.hasPermission("platform.update") && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(true);
                        setMenuOpen(false);
                      }}
                    >
                      <Pencil aria-hidden="true" />
                      Modifier
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      void platform.refetch();
                      setMenuOpen(false);
                    }}
                  >
                    <RefreshCw aria-hidden="true" />
                    Actualiser
                  </button>
                  {auth.hasPermission("platform.archive") && (
                    <button type="button" onClick={() => void archiveCurrent()}>
                      <Trash2 aria-hidden="true" />
                      Supprimer
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {archive.error && (
        <div className="form-error" role="alert">
          L’opération a échoué.
        </div>
      )}
      <div className="platform-detail-columns">
        {auth.hasPermission("service.read") && (
          <ServicesPanel
            platformId={platform.data.id}
            archived={Boolean(platform.data.archived_at)}
            categoriesOpen={categoriesOpen}
            onToggleCategories={() => setCategoriesOpen((current) => !current)}
          />
        )}
        {auth.hasPermission("history.read") && (
          <HistoryPanel platformId={platform.data.id} />
        )}
      </div>
      {editing && (
        <ModalPortal>
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setEditing(false);
            }}
          >
            <section
              className="settings-modal platform-create-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="edit-platform-title"
            >
              <div className="section-header">
                <h2 id="edit-platform-title">Modifier {platform.data.name}</h2>
                <button
                  type="button"
                  aria-label="Fermer"
                  data-tooltip="Fermer"
                  data-tooltip-placement="bottom"
                  onClick={() => setEditing(false)}
                >
                  <X aria-hidden="true" />
                </button>
              </div>
              <PlatformForm
                initial={platform.data}
                submitLabel="Enregistrer les modifications"
                pending={update.isPending}
                error={
                  update.error instanceof ApiError
                    ? update.error.message
                    : update.error
                      ? "Le serveur est indisponible."
                      : null
                }
                onSubmit={submit}
                onCancel={() => setEditing(false)}
              />
            </section>
          </div>
        </ModalPortal>
      )}
      {addingServices && (
        <ModalPortal>
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) closeAddServices();
            }}
          >
            <section
              className={`settings-modal add-services-modal add-services-modal--${addMethod}`}
              role="dialog"
              aria-modal="true"
              aria-labelledby="add-services-choice-title"
            >
              <div className="section-header">
                <div className="modal-title-actions">
                  {addMethod !== "choice" && (
                    <button
                      type="button"
                      aria-label="Retour aux méthodes"
                      data-tooltip="Retour aux méthodes"
                      data-tooltip-placement="bottom"
                      onClick={() => setAddMethod("choice")}
                    >
                      <ArrowLeft aria-hidden="true" />
                    </button>
                  )}
                  <h2 id="add-services-choice-title">
                    {addMethodTitles[addMethod]}
                  </h2>
                </div>
                <button
                  type="button"
                  aria-label="Fermer"
                  data-tooltip="Fermer"
                  data-tooltip-placement="bottom"
                  onClick={closeAddServices}
                >
                  <X aria-hidden="true" />
                </button>
              </div>
              <div className="add-services-modal__body">
              {addMethod === "choice" && (
                <div className="add-services-choice">
                  <p>Choisissez une méthode d’ajout.</p>
                  <div className="service-methods">
                    {auth.hasPermission("platform.scan") && (
                      <button
                        type="button"
                        onClick={() => setAddMethod("scan")}
                      >
                        <Radar aria-hidden="true" />
                        <span>
                          <strong>Scanner automatiquement</strong>
                          <small>
                            Détecter les services depuis une URL ou une adresse
                            IP.
                          </small>
                        </span>
                      </button>
                    )}
                    {auth.hasPermission("service.import") && (
                      <button
                        type="button"
                        onClick={() => setAddMethod("import")}
                      >
                        <FileSpreadsheet aria-hidden="true" />
                        <span>
                          <strong>Importer un fichier Excel</strong>
                          <small>
                            Associer les colonnes nom, version et catégorie.
                          </small>
                        </span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setAddMethod("manual")}
                    >
                      <ListPlus aria-hidden="true" />
                      <span>
                        <strong>Ajouter un à un</strong>
                        <small>
                          Saisir manuellement les services et leurs versions.
                        </small>
                      </span>
                    </button>
                  </div>
                </div>
              )}
              {addMethod === "scan" && (
                <ScanPlatformPage embedded onClose={closeAddServices} />
              )}
              {addMethod === "import" && (
                <ImportServicesPage embedded onClose={closeAddServices} />
              )}
              {addMethod === "manual" && (
                <AddServicesPage
                  embedded
                  onClose={closeAddServices}
                  onSwitchToImport={() => setAddMethod("import")}
                />
              )}
              </div>
            </section>
          </div>
        </ModalPortal>
      )}
    </section>
  );
}
