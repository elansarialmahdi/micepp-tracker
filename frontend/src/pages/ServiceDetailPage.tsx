import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, RefreshCw, ShieldAlert, Trash2 } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError } from "../api/client";
import {
  archiveService,
  getCategories,
  getService,
  updateService,
  checkService,
  getServiceVulnerabilities,
  type Category,
  type Service,
  type ServiceInput,
} from "../api/inventory";
import { useAuth } from "../auth/AuthProvider";
import { CustomSelect } from "../components/CustomSelect";

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
        <input
          id="edit-service-name"
          {...register("name", { required: true })}
        />
        {formState.errors.name && (
          <p className="field-error">Le nom est obligatoire.</p>
        )}
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
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>
          Annuler
        </button>
        <button className="primary-button" type="submit" disabled={pending}>
          Enregistrer
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
  const service = useQuery({
    queryKey: ["service", serviceId],
    queryFn: ({ signal }) => getService(serviceId, signal),
    refetchInterval: (query) =>
      query.state.data?.last_checked_at ? false : 1500,
  });
  const categories = useQuery({
    queryKey: ["categories", "global"],
    queryFn: ({ signal }) =>
      getCategories(service.data?.platform_id ?? "", signal),
    enabled: Boolean(service.data?.platform_id),
  });
  const update = useMutation({
    mutationFn: (input: ServiceInput) => updateService(serviceId, input),
  });
  const archive = useMutation({ mutationFn: () => archiveService(serviceId) });
  const vulnerabilities = useQuery({
    queryKey: ["service-vulnerabilities", serviceId],
    queryFn: ({ signal }) => getServiceVulnerabilities(serviceId, signal),
  });
  const check = useMutation({
    mutationFn: () => checkService(serviceId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["service", serviceId] }),
        queryClient.invalidateQueries({
          queryKey: ["cpe-candidates", serviceId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["service-vulnerabilities", serviceId],
        }),
      ]);
    },
  });

  if (service.isPending) return <p role="status">Chargement du service…</p>;
  if (service.isError || !service.data)
    return (
      <div className="form-error" role="alert">
        {service.error instanceof ApiError
          ? service.error.message
          : "Service introuvable."}
      </div>
    );
  const currentService = service.data;
  const platformId = service.data.platform_id;

  async function submit(input: ServiceInput) {
    const identityChanged =
      input.name !== currentService.name ||
      input.version !== currentService.version;
    const updated = await update.mutateAsync(input);
    queryClient.setQueryData(["service", serviceId], updated);
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["services", updated.platform_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["service-vulnerabilities", serviceId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["cpe-candidates", serviceId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["categories", updated.platform_id, "used"],
      }),
    ]);
    setEditing(false);
    if (identityChanged && auth.hasPermission("service.scan")) {
      try {
        await check.mutateAsync();
      } catch {
        // L'ancienne évaluation est déjà invalidée ; l'erreur est affichée dans la page.
      }
    }
  }

  async function archiveCurrent() {
    if (
      !window.confirm(
        "Supprimer ce service de l’affichage ? Ses données seront conservées.",
      )
    )
      return;
    await archive.mutateAsync();
    await queryClient.invalidateQueries({ queryKey: ["services", platformId] });
    navigate(`/platforms/${platformId}`);
  }

  return (
    <section aria-labelledby="service-title">
      <Link className="back-link back-link--button" to={`/platforms/${service.data.platform_id}`}>
        <ArrowLeft aria-hidden="true" />
        Retour à la plateforme
      </Link>
      <div className="page-header platform-detail-header">
        <div>
          <p className="eyebrow">Service</p>
          <h1 id="service-title">{service.data.name}</h1>
        </div>
        <div className="form-actions">
          {!service.data.archived_at &&
            auth.hasPermission("service.update") && (
              <button type="button" onClick={() => setEditing(true)}>
                <Pencil aria-hidden="true" />
                Modifier
              </button>
            )}
          {!service.data.archived_at &&
            auth.hasPermission("service.archive") && (
              <button type="button" onClick={() => void archiveCurrent()}>
                <Trash2 aria-hidden="true" />
                Supprimer
              </button>
            )}
          {!service.data.archived_at && auth.hasPermission("service.scan") && (
            <button
              className="primary-button"
              type="button"
              disabled={check.isPending}
              onClick={() => check.mutate()}
            >
              <RefreshCw aria-hidden="true" />
              {check.isPending ? "Vérification…" : "Vérifier automatiquement"}
            </button>
          )}
        </div>
      </div>
      <dl className="detail-list">
        <div>
          <dt>Version</dt>
          <dd>{service.data.version ?? "Non renseignée"}</dd>
        </div>
        <div>
          <dt>Catégorie</dt>
          <dd>{service.data.category_name ?? "Non catégorisé"}</dd>
        </div>
        <div>
          <dt>Dernière vérification</dt>
          <dd>{service.data.last_checked_at ?? "Jamais"}</dd>
        </div>
      </dl>
      {check.isError && (
        <div className="form-error" role="alert">
          {check.error instanceof ApiError
            ? check.error.message
            : "La vérification de sécurité a échoué."}
        </div>
      )}
      {check.isPending && (
        <p role="status">
          Vérification de {service.data.name}{" "}
          {service.data.version ?? "sans version renseignée"} avec OSV et la
          NVD…
        </p>
      )}
      <section className="vulnerability-panel" aria-labelledby="cpe-title">
        <h2 id="cpe-title">Identification de sécurité</h2>
        {service.data.security_identity?.status === "verified" &&
        service.data.security_identity.source?.includes("OSV") ? (
          <p>
            <strong>Paquet validé automatiquement :</strong>{" "}
            <code>
              {service.data.security_identity.ecosystem}:
              {service.data.security_identity.package}@
              {service.data.security_identity.version}
            </code>{" "}
            via {service.data.security_identity.source}.
            {service.data.cpe_uri ? (
              <>
                {" "}
                CPE complémentaire : <code>{service.data.cpe_uri}</code>.
              </>
            ) : (
              " Aucun CPE n’est nécessaire."
            )}
          </p>
        ) : service.data.cpe_uri ? (
          <p>
            <strong>CPE retenu automatiquement :</strong>{" "}
            <code>{service.data.cpe_uri}</code> (
            {Math.round((service.data.cpe_match_confidence ?? 0) * 100)} %,{" "}
            {service.data.cpe_match_method})
          </p>
        ) : service.data.security_identity?.status === "version_not_found" ? (
          <p className="field-error">
            La version {service.data.version} est introuvable dans les registres
            de paquets et aucun CPE exact n’a été trouvé. Vérifiez le nom et la
            version du service.
          </p>
        ) : (
          <p>
            Aucune identité automatique fiable n’a été trouvée. Vérifiez le nom
            et la version du service.
          </p>
        )}
      </section>
      <section
        className="vulnerability-panel"
        aria-labelledby="vulnerabilities-title"
      >
        <div className="section-header">
          <h2 id="vulnerabilities-title">
            <ShieldAlert aria-hidden="true" /> Vulnérabilités de la version
            actuelle
          </h2>
          <span className="badge">
            {service.data.last_checked_at
              ? `${vulnerabilities.data?.length ?? 0} actives`
              : "Non vérifié"}
          </span>
        </div>
        {vulnerabilities.isPending ? (
          <p role="status">Chargement des vulnérabilités…</p>
        ) : !service.data.last_checked_at ? (
          <p className="empty-state">
            La vérification automatique est en attente.
          </p>
        ) : ["version_not_found", "ambiguous_ecosystem"].includes(
            service.data.security_identity?.status ?? "",
          ) && !service.data.cpe_uri ? (
          <p className="empty-state">
            Impossible de conclure sur les vulnérabilités tant que l’identité
            exacte du service n’est pas validée.
          </p>
        ) : !vulnerabilities.data?.length ? (
          <p className="empty-state">
            Aucune vulnérabilité connue n’a été trouvée pour {service.data.name}{" "}
            {service.data.version ?? "(version non renseignée)"} dans les
            sources consultées.
          </p>
        ) : (
          <div className="table-wrapper">
            <table className="service-table">
              <thead>
                <tr>
                  <th>Identifiant</th>
                  <th>Sévérité</th>
                  <th>Description</th>
                  <th>Détail</th>
                </tr>
              </thead>
              <tbody>
                {vulnerabilities.data.map((item) => (
                  <tr key={item.link_id}>
                    <td>
                      <strong>{item.cve_id}</strong>
                    </td>
                    <td>
                      <span
                        className={`badge severity-${item.severity ?? "unknown"}`}
                      >
                        {item.severity ?? "inconnue"} {item.cvss_score ?? "—"}
                      </span>
                    </td>
                    <td>
                      {item.description.slice(0, 180)}
                      {item.description.length > 180 ? "…" : ""}
                    </td>
                    <td>
                      <Link to={`/vulnerabilities/${item.link_id}`}>Voir</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {editing && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setEditing(false);
          }}
        >
          <section
            className="settings-modal service-edit-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-service-modal-title"
          >
            <h2 id="edit-service-modal-title">Modifier {service.data.name}</h2>
            <ServiceEditForm
              service={service.data}
              categories={categories.data ?? []}
              pending={update.isPending}
              error={
                update.error instanceof ApiError
                  ? update.error.message
                  : update.error
                    ? "La modification a échoué."
                    : null
              }
              onSubmit={submit}
              onCancel={() => setEditing(false)}
            />
          </section>
        </div>
      )}
    </section>
  );
}
