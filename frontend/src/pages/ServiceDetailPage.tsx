import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  History,
  Pencil,
  Plus,
  PowerOff,
  RefreshCw,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError } from "../api/client";
import {
  archiveService,
  checkService,
  createManualVulnerability,
  getCategories,
  getService,
  getServiceVulnerabilities,
  setVulnerabilityIgnored,
  updateService,
  updateServiceCpe,
  type Category,
  type ManualVulnerabilityInput,
  type Service,
  type ServiceInput,
} from "../api/inventory";
import { useAuth } from "../auth/AuthProvider";
import { CustomSelect } from "../components/CustomSelect";
import { ModalPortal } from "../components/ModalPortal";

export function formatDateTime(value: string | null): string {
  if (!value) return "Jamais";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date inconnue";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function ModalHeader({ id, title, onClose }: { id: string; title: string; onClose: () => void }) {
  return (
    <div className="section-header">
      <h2 id={id}>{title}</h2>
      <button type="button" aria-label="Fermer" onClick={onClose}>
        <X aria-hidden="true" />
      </button>
    </div>
  );
}

function ServiceEditForm({
  service,
  categories,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  service: Service;
  categories: Category[];
  pending: boolean;
  error: string | null;
  onSubmit: (input: ServiceInput) => Promise<void>;
  onCancel: () => void;
}) {
  const { control, register, handleSubmit, formState } = useForm({
    defaultValues: {
      name: service.name,
      version: service.version ?? "",
      category_id: service.category_id ?? "",
    },
  });
  return (
    <form
      className="platform-form"
      onSubmit={handleSubmit(async (values) =>
        onSubmit({
          name: values.name.trim(),
          version: values.version.trim() || null,
          category_id: values.category_id || null,
        }),
      )}
    >
      <div className="form-field">
        <label htmlFor="edit-service-name">Nom</label>
        <input id="edit-service-name" {...register("name", { required: true })} />
        {formState.errors.name && <p className="field-error">Le nom est obligatoire.</p>}
      </div>
      <div className="form-field">
        <label htmlFor="edit-service-version">Version</label>
        <input id="edit-service-version" {...register("version")} />
      </div>
      <div className="form-field">
        <label htmlFor="edit-service-category">Catégorie</label>
        <Controller
          control={control}
          name="category_id"
          render={({ field }) => (
            <CustomSelect
              id="edit-service-category"
              value={field.value}
              onChange={field.onChange}
              options={[
                { value: "", label: "Non catégorisé" },
                ...categories.map((category) => ({ value: category.id, label: category.name })),
              ]}
            />
          )}
        />
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>Annuler</button>
        <button className="primary-button" type="submit" disabled={pending}>Enregistrer</button>
      </div>
    </form>
  );
}

function ManualVulnerabilityForm({
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  pending: boolean;
  error: string | null;
  onSubmit: (input: ManualVulnerabilityInput) => Promise<void>;
  onCancel: () => void;
}) {
  const { control, register, handleSubmit, formState } = useForm({
    defaultValues: {
      identifier: "",
      title: "",
      description: "",
      severity: "unknown",
      cvss_score: "",
      reference_url: "",
    },
  });
  return (
    <form
      className="platform-form manual-vulnerability-form"
      noValidate
      onSubmit={handleSubmit(async (values) =>
        onSubmit({
          identifier: values.identifier.trim() || null,
          title: values.title.trim() || null,
          description: values.description.trim(),
          severity: values.severity as ManualVulnerabilityInput["severity"],
          cvss_score: values.cvss_score === "" ? null : Number(values.cvss_score),
          reference_url: values.reference_url.trim() || null,
        }),
      )}
    >
      <div className="form-field">
        <label htmlFor="manual-vulnerability-id">Identifiant (optionnel)</label>
        <input
          id="manual-vulnerability-id"
          placeholder="Généré automatiquement : MANUEL-XXXXXXXX"
          {...register("identifier")}
        />
      </div>
      <div className="form-field">
        <label htmlFor="manual-vulnerability-title">Titre (optionnel)</label>
        <input id="manual-vulnerability-title" {...register("title")} />
      </div>
      <div className="manual-vulnerability-form__row">
        <div className="form-field">
          <label htmlFor="manual-vulnerability-severity">Sévérité (optionnelle)</label>
          <Controller
            control={control}
            name="severity"
            render={({ field }) => (
              <CustomSelect
                id="manual-vulnerability-severity"
                value={field.value}
                onChange={field.onChange}
                options={[
                  { value: "unknown", label: "Inconnue" },
                  { value: "low", label: "Faible" },
                  { value: "medium", label: "Moyenne" },
                  { value: "high", label: "Élevée" },
                  { value: "critical", label: "Critique" },
                ]}
              />
            )}
          />
        </div>
        <div className="form-field">
          <label htmlFor="manual-vulnerability-score">Score CVSS (optionnel)</label>
          <input
            id="manual-vulnerability-score"
            type="number"
            min="0"
            max="10"
            step="0.1"
            {...register("cvss_score", { min: 0, max: 10 })}
          />
        </div>
      </div>
      <div className="form-field">
        <label htmlFor="manual-vulnerability-description">Description</label>
        <textarea
          id="manual-vulnerability-description"
          rows={5}
          {...register("description", { required: "La description est obligatoire." })}
        />
        {formState.errors.description && <p className="field-error">{formState.errors.description.message}</p>}
      </div>
      <div className="form-field">
        <label htmlFor="manual-vulnerability-reference">Référence (URL, optionnelle)</label>
        <input id="manual-vulnerability-reference" type="url" placeholder="https://…" {...register("reference_url")} />
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>Annuler</button>
        <button className="primary-button" type="submit" disabled={pending}>
          {pending ? "Ajout…" : "Ajouter la vulnérabilité"}
        </button>
      </div>
    </form>
  );
}

function CpeForm({
  current,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  current: string | null;
  pending: boolean;
  error: string | null;
  onSubmit: (cpe: string) => Promise<void>;
  onCancel: () => void;
}) {
  const { register, handleSubmit, formState } = useForm({ defaultValues: { cpe: current ?? "" } });
  return (
    <form className="platform-form" onSubmit={handleSubmit(async ({ cpe }) => onSubmit(cpe.trim()))}>
      <p className="modal-help-text">
        Le CPE sera vérifié dans la NVD avant de remplacer l’identification actuelle.
      </p>
      <div className="form-field">
        <label htmlFor="manual-cpe">CPE 2.3</label>
        <input
          id="manual-cpe"
          placeholder="cpe:2.3:a:éditeur:produit:version:*:*:*:*:*:*:*"
          {...register("cpe", { required: "Le CPE est obligatoire." })}
        />
        {formState.errors.cpe && <p className="field-error">{formState.errors.cpe.message}</p>}
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>Annuler</button>
        <button className="primary-button" type="submit" disabled={pending}>
          {pending ? "Vérification…" : "Vérifier et remplacer"}
        </button>
      </div>
    </form>
  );
}

export function ServiceDetailPage() {
  const { serviceId = "" } = useParams();
  const auth = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [addingManual, setAddingManual] = useState(false);
  const [editingCpe, setEditingCpe] = useState(false);
  const [vulnerabilityView, setVulnerabilityView] = useState<"active" | "history">("active");

  const service = useQuery({
    queryKey: ["service", serviceId],
    queryFn: ({ signal }) => getService(serviceId, signal),
    refetchInterval: (query) =>
      query.state.data?.last_checked_at || query.state.data?.cpe_enabled === false ? false : 1500,
  });
  const categories = useQuery({
    queryKey: ["categories", "global"],
    queryFn: ({ signal }) => getCategories(service.data?.platform_id ?? "", signal),
    enabled: Boolean(service.data?.platform_id),
  });
  const vulnerabilities = useQuery({
    queryKey: ["service-vulnerabilities", serviceId, vulnerabilityView],
    queryFn: ({ signal }) => getServiceVulnerabilities(serviceId, signal, vulnerabilityView),
  });
  const update = useMutation({ mutationFn: (input: ServiceInput) => updateService(serviceId, input) });
  const archive = useMutation({ mutationFn: () => archiveService(serviceId) });
  const check = useMutation({
    mutationFn: () => checkService(serviceId),
    onSuccess: () => invalidateServiceData(),
  });
  const cpe = useMutation({
    mutationFn: (input: { enabled: boolean; cpe_uri?: string | null }) => updateServiceCpe(serviceId, input),
    onSuccess: async (updated) => {
      queryClient.setQueryData(["service", serviceId], updated);
      await invalidateServiceData();
    },
  });
  const manual = useMutation({
    mutationFn: (input: ManualVulnerabilityInput) => createManualVulnerability(serviceId, input),
    onSuccess: async () => {
      setVulnerabilityView("active");
      setAddingManual(false);
      await invalidateServiceData();
    },
  });
  const reactivate = useMutation({
    mutationFn: (linkId: string) => setVulnerabilityIgnored(linkId, false),
    onSuccess: () => invalidateServiceData(),
  });

  async function invalidateServiceData() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["service", serviceId] }),
      queryClient.invalidateQueries({ queryKey: ["cpe-candidates", serviceId] }),
      queryClient.invalidateQueries({ queryKey: ["service-vulnerabilities", serviceId] }),
      queryClient.invalidateQueries({ queryKey: ["services", service.data?.platform_id] }),
      queryClient.invalidateQueries({ queryKey: ["platform-history", service.data?.platform_id] }),
    ]);
  }

  if (service.isPending) return <p role="status">Chargement du service…</p>;
  if (service.isError || !service.data) {
    return (
      <div className="form-error" role="alert">
        {service.error instanceof ApiError ? service.error.message : "Service introuvable."}
      </div>
    );
  }
  const currentService = service.data;
  const platformId = currentService.platform_id;

  async function submit(input: ServiceInput) {
    const identityChanged = input.name !== currentService.name || input.version !== currentService.version;
    const updated = await update.mutateAsync(input);
    queryClient.setQueryData(["service", serviceId], updated);
    await invalidateServiceData();
    setEditing(false);
    if (identityChanged && updated.cpe_enabled && auth.hasPermission("service.scan")) {
      try {
        await check.mutateAsync();
      } catch {
        // L’ancienne évaluation est invalidée ; l’erreur reste affichée dans la page.
      }
    }
  }

  async function archiveCurrent() {
    if (!window.confirm("Supprimer ce service de l’affichage ? Ses données seront conservées.")) return;
    await archive.mutateAsync();
    await queryClient.invalidateQueries({ queryKey: ["services", platformId] });
    navigate(`/platforms/${platformId}`);
  }

  const mutationError = (value: unknown, fallback: string) =>
    value instanceof ApiError ? value.message : value ? fallback : null;

  return (
    <section className="service-detail-page" aria-labelledby="service-title">
      <div className="service-detail-columns">
        <div className="service-overview-panel">
          <Link className="back-link back-link--button" to={`/platforms/${platformId}`}>
            <ArrowLeft aria-hidden="true" />
            Retour à la plateforme
          </Link>
          <div className="page-header platform-detail-header">
            <div>
              <p className="eyebrow">Service</p>
              <h1 id="service-title">{currentService.name}</h1>
            </div>
            <div className="form-actions">
              {!currentService.archived_at && auth.hasPermission("service.update") && (
                <button className="service-action-button" type="button" onClick={() => setEditing(true)} aria-label="Modifier le service" data-tooltip="Modifier">
                  <Pencil aria-hidden="true" />
                </button>
              )}
              {!currentService.archived_at && auth.hasPermission("service.archive") && (
                <button className="service-action-button" type="button" onClick={() => void archiveCurrent()} aria-label="Supprimer le service" data-tooltip="Supprimer">
                  <Trash2 aria-hidden="true" />
                </button>
              )}
              {!currentService.archived_at && currentService.cpe_enabled && auth.hasPermission("service.scan") && (
                <button className="service-action-button" type="button" disabled={check.isPending} onClick={() => check.mutate()} aria-label="Vérifier automatiquement" data-tooltip="Vérifier automatiquement">
                  <RefreshCw className={check.isPending ? "is-spinning" : undefined} aria-hidden="true" />
                </button>
              )}
            </div>
          </div>
          <dl className="detail-list">
            <div><dt>Version</dt><dd>{currentService.version ?? "Non renseignée"}</dd></div>
            <div><dt>Catégorie</dt><dd>{currentService.category_name ?? "Non catégorisé"}</dd></div>
            <div>
              <dt>Dernière vérification</dt>
              <dd>{currentService.last_checked_at ? <time dateTime={currentService.last_checked_at}>{formatDateTime(currentService.last_checked_at)}</time> : "Jamais"}</dd>
            </div>
          </dl>
          {check.isError && <div className="form-error" role="alert">{mutationError(check.error, "La vérification de sécurité a échoué.")}</div>}
          {cpe.isError && <div className="form-error" role="alert">{mutationError(cpe.error, "La modification du CPE a échoué.")}</div>}
          {check.isPending && <p role="status">Vérification de {currentService.name} avec OSV et la NVD…</p>}

          <section className="vulnerability-panel security-identification" aria-labelledby="cpe-title">
            <div className="security-identification__header">
              <h2 id="cpe-title">Identification de sécurité</h2>
              {auth.hasPermission("service.scan") && (
                <div className="security-identification__actions">
                  <button type="button" onClick={() => setEditingCpe(true)}>
                    {currentService.cpe_uri ? "Remplacer le CPE" : "Saisir un CPE"}
                  </button>
                  <button
                    type="button"
                    disabled={cpe.isPending}
                    onClick={() => cpe.mutate({ enabled: !currentService.cpe_enabled })}
                  >
                    <PowerOff aria-hidden="true" />
                    {currentService.cpe_enabled ? "Désactiver le CPE" : "Réactiver l’automatique"}
                  </button>
                </div>
              )}
            </div>
            {!currentService.cpe_enabled ? (
              <p className="security-identification__disabled">
                La recherche automatique est désactivée. Seules les vulnérabilités saisies manuellement seront suivies.
              </p>
            ) : currentService.security_identity?.status === "verified" && currentService.security_identity.source?.includes("OSV") ? (
              <p><strong>Paquet validé :</strong> <code>{currentService.security_identity.ecosystem}:{currentService.security_identity.package}@{currentService.security_identity.version}</code> via {currentService.security_identity.source}.{currentService.cpe_uri && <> CPE : <code>{currentService.cpe_uri}</code>.</>}</p>
            ) : currentService.cpe_uri ? (
              <p><strong>CPE retenu :</strong> <code>{currentService.cpe_uri}</code> ({Math.round((currentService.cpe_match_confidence ?? 0) * 100)} %, {currentService.cpe_match_method})</p>
            ) : currentService.security_identity?.status === "version_not_found" ? (
              <p className="field-error">La version {currentService.version} est introuvable et aucun CPE exact n’a été trouvé.</p>
            ) : (
              <p>Aucune identité automatique fiable n’a été trouvée. Vous pouvez saisir un CPE vérifié manuellement.</p>
            )}
          </section>
        </div>

        <section className="vulnerability-panel service-vulnerabilities-panel" aria-labelledby="vulnerabilities-title">
          <div className="section-header service-vulnerabilities-header">
            <h2 id="vulnerabilities-title">
              {vulnerabilityView === "history" ? <History aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
              {vulnerabilityView === "history" ? "Anciennes vulnérabilités" : "Vulnérabilités actuelles"}
            </h2>
            <div className="vulnerability-list-actions">
              <span className="badge">{vulnerabilities.data?.length ?? 0}</span>
              <button type="button" onClick={() => setVulnerabilityView(vulnerabilityView === "active" ? "history" : "active")}>
                {vulnerabilityView === "active" ? "Anciennes vulnérabilités" : "Vulnérabilités actuelles"}
              </button>
              {auth.hasPermission("service.scan") && (
                <button className="primary-button" type="button" onClick={() => setAddingManual(true)}>
                  <Plus aria-hidden="true" /> Ajouter
                </button>
              )}
            </div>
          </div>
          {vulnerabilities.isPending ? (
            <p role="status">Chargement des vulnérabilités…</p>
          ) : !vulnerabilities.data?.length ? (
            <p className="empty-state">
              {vulnerabilityView === "history"
                ? "Aucune ancienne vulnérabilité pour ce service."
                : currentService.cpe_enabled
                  ? "Aucune vulnérabilité active connue."
                  : "Aucune vulnérabilité manuelle active."}
            </p>
          ) : (
            <div className="table-wrapper">
              <table className="service-table">
                <thead><tr><th>Identifiant</th><th>Sévérité</th><th>Description</th><th>Actions</th></tr></thead>
                <tbody>
                  {vulnerabilities.data.map((item) => (
                    <tr key={item.link_id}>
                      <td><strong>{item.cve_id}</strong></td>
                      <td><span className={`badge severity-${item.severity ?? "unknown"}`}>{item.severity ?? "inconnue"} {item.cvss_score ?? "—"}</span></td>
                      <td className="vulnerability-description-cell"><span className="vulnerability-description">{item.description.slice(0, 180)}{item.description.length > 180 ? "…" : ""}</span></td>
                      <td>
                        <div className="vulnerability-row-actions">
                          <Link to={`/vulnerabilities/${item.link_id}`}>Voir</Link>
                          {vulnerabilityView === "history" && auth.hasPermission("service.scan") && (
                            <button type="button" disabled={reactivate.isPending} onClick={() => reactivate.mutate(item.link_id)}>Réactiver</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {reactivate.isError && <div className="form-error" role="alert">{mutationError(reactivate.error, "La réactivation a échoué.")}</div>}
        </section>
      </div>

      {editing && (
        <ModalPortal><div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setEditing(false)}>
          <section className="settings-modal service-edit-modal" role="dialog" aria-modal="true" aria-labelledby="edit-service-modal-title">
            <ModalHeader id="edit-service-modal-title" title={`Modifier ${currentService.name}`} onClose={() => setEditing(false)} />
            <ServiceEditForm service={currentService} categories={categories.data ?? []} pending={update.isPending} error={mutationError(update.error, "La modification a échoué.")} onSubmit={submit} onCancel={() => setEditing(false)} />
          </section>
        </div></ModalPortal>
      )}
      {addingManual && (
        <ModalPortal><div className="modal-backdrop form-modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setAddingManual(false)}>
          <section className="settings-modal form-dialog manual-vulnerability-modal" role="dialog" aria-modal="true" aria-labelledby="manual-vulnerability-modal-title">
            <ModalHeader id="manual-vulnerability-modal-title" title="Ajouter une vulnérabilité" onClose={() => setAddingManual(false)} />
            <ManualVulnerabilityForm pending={manual.isPending} error={mutationError(manual.error, "L’ajout a échoué.")} onSubmit={(input) => manual.mutateAsync(input).then(() => undefined)} onCancel={() => setAddingManual(false)} />
          </section>
        </div></ModalPortal>
      )}
      {editingCpe && (
        <ModalPortal><div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setEditingCpe(false)}>
          <section className="settings-modal cpe-edit-modal" role="dialog" aria-modal="true" aria-labelledby="cpe-edit-modal-title">
            <ModalHeader id="cpe-edit-modal-title" title="Saisir un CPE" onClose={() => setEditingCpe(false)} />
            <CpeForm current={currentService.cpe_uri} pending={cpe.isPending} error={mutationError(cpe.error, "La vérification du CPE a échoué.")} onSubmit={async (value) => { await cpe.mutateAsync({ enabled: true, cpe_uri: value }); setEditingCpe(false); }} onCancel={() => setEditingCpe(false)} />
          </section>
        </div></ModalPortal>
      )}
    </section>
  );
}
