import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CircleAlert,
  LoaderCircle,
  Radar,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { getPlatform } from "../api/platforms";
import {
  cancelScan,
  confirmScan,
  getScan,
  launchScan,
  type DetectedService,
  type ScanConfirmationItem,
  type ScanJob,
} from "../api/scans";
import { useAuth } from "../auth/AuthProvider";
import { CategoryPicker } from "../components/CategoryPicker";
import { CustomSelect } from "../components/CustomSelect";
import { AICategorizationReview } from "../features/categorization/AICategorizationReview";

function detectionKey(item: DetectedService): string {
  return `${item.detected_name.trim().toLocaleLowerCase("fr-FR")}\u0000${
    item.detected_version?.trim().toLocaleLowerCase("fr-FR") ?? ""
  }`;
}

export function dedupeScanDetections(items: DetectedService[]): DetectedService[] {
  const unique = new Map<string, DetectedService>();
  items.forEach((item) => {
    const key = detectionKey(item);
    const current = unique.get(key);
    if (!current || item.confidence > current.confidence) unique.set(key, item);
  });
  return [...unique.values()];
}

export function ScanPlatformPage({
  embedded = false,
  onClose,
}: {
  embedded?: boolean;
  onClose?: () => void;
} = {}) {
  const { platformId = "" } = useParams();
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [scanId, setScanId] = useState<string | null>(null);
  const [target, setTarget] = useState("");
  const [scanType, setScanType] = useState<"full" | "ports" | "web">("full");
  const platform = useQuery({
    queryKey: ["platform", platformId],
    queryFn: ({ signal }) => getPlatform(platformId, signal),
  });
  const launch = useMutation({
    mutationFn: () =>
      launchScan(platformId, {
        target: target || undefined,
        scan_type: scanType,
      }),
    onSuccess: (job) => {
      setScanId(job.id);
      queryClient.setQueryData(["scan", job.id], job);
    },
  });
  const scan = useQuery({
    queryKey: ["scan", scanId],
    queryFn: ({ signal }) => getScan(scanId!, signal),
    enabled: Boolean(scanId),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status ?? "")
        ? 1000
        : false,
  });
  const cancel = useMutation({
    mutationFn: () => cancelScan(scanId!),
    onSuccess: (job) => queryClient.setQueryData(["scan", job.id], job),
  });

  if (!auth.hasPermission("platform.scan")) {
    return (
      <div className="form-error" role="alert">
        Vous n’avez pas l’autorisation de lancer un scan.
      </div>
    );
  }

  const job = scan.data ?? launch.data;
  const error = launch.error ?? scan.error ?? cancel.error;

  return (
    <section
      className={`scan-page${embedded ? " scan-page--embedded" : ""}`}
      aria-labelledby={embedded ? undefined : "scan-title"}
      aria-label={embedded ? "Assistant de scan des services" : undefined}
    >
      {!embedded && (
        <header className="scan-page__header">
          <div>
            <p className="eyebrow">Inventaire automatique</p>
            <h1 id="scan-title">Scanner {platform.data?.name ?? "la plateforme"}</h1>
          </div>
          <Link className="back-link" to={`/platforms/${platformId}`}>
            <ArrowLeft aria-hidden="true" />
            Retour à la plateforme
          </Link>
        </header>
      )}

      {!job && (
        <form
          className="scan-form"
          onSubmit={(event) => {
            event.preventDefault();
            launch.mutate();
          }}
        >
          <div className="form-field scan-form__target">
            <label htmlFor="scan-target">Cible</label>
            <input
              id="scan-target"
              value={target}
              placeholder={platform.data?.normalized_target ?? "Cible obligatoire"}
              onChange={(event) => setTarget(event.target.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor="scan-type">Périmètre</label>
            <CustomSelect
              id="scan-type"
              value={scanType}
              onChange={(next) => setScanType(next as "full" | "ports" | "web")}
              options={[
                { value: "full", label: "Complet" },
                { value: "ports", label: "Ports et services" },
                { value: "web", label: "Technologies web" },
              ]}
            />
          </div>
          <button className="primary-button scan-launch-button" type="submit" disabled={launch.isPending}>
            <Radar aria-hidden="true" />
            {launch.isPending ? "Lancement…" : "Lancer le scan"}
          </button>
        </form>
      )}

      {error && (
        <div className="form-error" role="alert">
          {error instanceof ApiError ? error.message : "Le scan a échoué."}
        </div>
      )}
      {job && job.status !== "succeeded" && (
        <ScanProgress job={job} onCancel={() => cancel.mutate()} />
      )}
      {job?.status === "succeeded" && (
        <ScanResults job={job} platformId={platformId} onClose={onClose} />
      )}
    </section>
  );
}

function ScanProgress({ job, onCancel }: { job: ScanJob; onCancel: () => void }) {
  const active = ["queued", "running"].includes(job.status);
  const step = job.current_step
    ? `${job.current_step.charAt(0).toLocaleUpperCase("fr-FR")}${job.current_step.slice(1)}`
    : "Préparation du scan";

  return (
    <section
      className={`scan-progress scan-progress--${job.status}`}
      aria-labelledby="scan-progress-title"
    >
      <div className="scan-progress__header">
        <span className="scan-progress__icon" aria-hidden="true">
          {job.status === "failed" ? (
            <CircleAlert />
          ) : (
            <LoaderCircle className={active ? "is-spinning" : undefined} />
          )}
        </span>
        <div>
          <p className="eyebrow">{job.status === "queued" ? "Préparation" : "Analyse en cours"}</p>
          <h2 id="scan-progress-title">{step}</h2>
        </div>
        <strong>{job.progress}%</strong>
      </div>
      <progress max="100" value={job.progress} aria-label={`Progression : ${job.progress} %`}>
        {job.progress}%
      </progress>
      <footer className="scan-progress__footer">
        <span role="status">{job.target}</span>
        {active && (
          <button type="button" onClick={onCancel}>
            <X aria-hidden="true" />
            Annuler
          </button>
        )}
      </footer>
      {job.status === "failed" && (
        <div className="form-error" role="alert">
          {job.sanitized_error ?? "Le scan a échoué."}
        </div>
      )}
    </section>
  );
}

function ScanResults({
  job,
  platformId,
  onClose,
}: {
  job: ScanJob;
  platformId: string;
  onClose?: () => void;
}) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const detections = useMemo(() => dedupeScanDetections(job.detections), [job.detections]);
  const [items, setItems] = useState<ScanConfirmationItem[]>(() =>
    detections.map((item) => ({
      detected_service_id: item.id,
      selected: item.selected_for_import,
      name: item.detected_name,
      version: item.detected_version,
      category: item.category_suggestion,
    })),
  );
  const confirmation = useMutation({
    mutationFn: () => confirmScan(job.id, items),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["services", platformId] });
      await queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
  });
  const update = (id: string, changes: Partial<ScanConfirmationItem>) =>
    setItems((current) =>
      current.map((item) =>
        item.detected_service_id === id ? { ...item, ...changes } : item,
      ),
    );
  const selectedCount = items.filter((item) => item.selected).length;
  const duplicateCount = job.detections.length - detections.length;

  return (
    <section className="scan-results" aria-labelledby="scan-results-title">
      <header className="scan-results__header">
        <div>
          <p className="eyebrow">Inventaire détecté</p>
          <h2 id="scan-results-title">Services détectés</h2>
          <p>
            {items.length} service{items.length > 1 ? "s" : ""} unique{items.length > 1 ? "s" : ""}
            {duplicateCount > 0 ? `, ${duplicateCount} doublon${duplicateCount > 1 ? "s" : ""} fusionné${duplicateCount > 1 ? "s" : ""}` : ""}
          </p>
        </div>
        <AICategorizationReview
          platformId={platformId}
          items={items
            .filter((item) => item.selected)
            .map((item) => ({
              key: item.detected_service_id,
              name: item.name,
              version: item.version,
            }))}
          disabled={!selectedCount}
          onConfirmed={async (suggestions) => {
            const byId = new Map(
              suggestions.map((item) => [item.key, item.category?.name ?? null]),
            );
            setItems((current) =>
              current.map((item) => ({
                ...item,
                category: byId.has(item.detected_service_id)
                  ? byId.get(item.detected_service_id) ?? null
                  : item.category,
              })),
            );
            await queryClient.invalidateQueries({ queryKey: ["categories"] });
          }}
        />
      </header>

      <div className="scan-service-list" role="list" aria-label="Services à ajouter">
        <div className="scan-service-list__head" aria-hidden="true">
          <span>Ajouter</span>
          <span>Service</span>
          <span>Version</span>
          <span>Catégorie</span>
        </div>
        {items.map((item) => {
          return (
            <article
              className={`scan-service-row${item.selected ? " scan-service-row--selected" : ""}`}
              role="listitem"
              key={item.detected_service_id}
            >
              <label className="scan-service-row__select">
                <span className="scan-field-label">Ajouter</span>
                <input
                  aria-label={`Ajouter ${item.name}`}
                  type="checkbox"
                  checked={item.selected}
                  onChange={(event) =>
                    update(item.detected_service_id, { selected: event.target.checked })
                  }
                />
              </label>
              <label className="scan-result-field">
                <span className="scan-field-label">Service</span>
                <input
                  aria-label={`Nom ${item.name}`}
                  value={item.name}
                  disabled={!item.selected}
                  onChange={(event) =>
                    update(item.detected_service_id, { name: event.target.value })
                  }
                />
              </label>
              <label className="scan-result-field">
                <span className="scan-field-label">Version</span>
                <input
                  aria-label={`Version ${item.name}`}
                  value={item.version ?? ""}
                  disabled={!item.selected}
                  placeholder="Non renseignée"
                  onChange={(event) =>
                    update(item.detected_service_id, { version: event.target.value || null })
                  }
                />
              </label>
              <div className="scan-result-field">
                <span className="scan-field-label">Catégorie</span>
                <CategoryPicker
                  platformId={platformId}
                  ariaLabel={`Catégorie ${item.name}`}
                  value={item.category}
                  valueType="name"
                  disabled={!item.selected}
                  allowCreate={auth.hasPermission("service.create")}
                  onChange={(category) =>
                    update(item.detected_service_id, { category })
                  }
                />
              </div>
            </article>
          );
        })}
      </div>

      {confirmation.error && (
        <div className="form-error" role="alert">
          {confirmation.error instanceof ApiError
            ? confirmation.error.message
            : "La confirmation a échoué."}
        </div>
      )}
      {confirmation.data ? (
        <div className="success-message scan-results__success" role="status">
          <span>{confirmation.data.created} service(s) ajouté(s).</span>
          {onClose ? (
            <button type="button" onClick={onClose}>Terminer</button>
          ) : (
            <Link to={`/platforms/${platformId}`}>Retour à la plateforme</Link>
          )}
        </div>
      ) : (
        <footer className="scan-results__actions">
          <span>{selectedCount} service{selectedCount > 1 ? "s" : ""} sélectionné{selectedCount > 1 ? "s" : ""}</span>
          <button
            className="primary-button"
            type="button"
            onClick={() => confirmation.mutate()}
            disabled={confirmation.isPending || !selectedCount}
          >
            {confirmation.isPending ? "Ajout en cours…" : "Confirmer les services"}
          </button>
        </footer>
      )}
    </section>
  );
}
