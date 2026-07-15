import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Radar } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { getPlatform } from "../api/platforms";
import {
  cancelScan,
  confirmScan,
  getScan,
  launchScan,
  type ScanConfirmationItem,
  type ScanJob,
} from "../api/scans";
import { useAuth } from "../auth/AuthProvider";
import { CustomSelect } from "../components/CustomSelect";
import { AICategorizationReview } from "../features/categorization/AICategorizationReview";

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
  const platform = useQuery({
    queryKey: ["platform", platformId],
    queryFn: ({ signal }) => getPlatform(platformId, signal),
  });
  const [target, setTarget] = useState("");
  const [scanType, setScanType] = useState<"full" | "ports" | "web">("full");
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

  if (!auth.hasPermission("platform.scan"))
    return (
      <div className="form-error" role="alert">
        Vous n’avez pas l’autorisation de lancer un scan.
      </div>
    );
  const job = scan.data ?? launch.data;
  const error = launch.error ?? scan.error ?? cancel.error;

  return (
    <section
      className="scan-page"
      aria-labelledby={embedded ? undefined : "scan-title"}
      aria-label={embedded ? "Assistant de scan des services" : undefined}
    >
      {!embedded && (
        <>
          <p className="eyebrow">Détection contrôlée</p>
          <h1 id="scan-title">
            Scanner {platform.data?.name ?? "la plateforme"}
          </h1>
        </>
      )}
      {!embedded && (
        <Link className="back-link" to={`/platforms/${platformId}`}>
          <ArrowLeft aria-hidden="true" />
          Retour à la plateforme
        </Link>
      )}
      {!job && (
        <form
          className="scan-form"
          onSubmit={(event) => {
            event.preventDefault();
            launch.mutate();
          }}
        >
          <div className="form-field">
            <label htmlFor="scan-target">Cible temporaire</label>
            <input
              id="scan-target"
              value={target}
              placeholder={
                platform.data?.normalized_target ?? "Cible obligatoire"
              }
              onChange={(event) => setTarget(event.target.value)}
            />
            <small>
              Laissez vide pour utiliser la cible enregistrée de la plateforme.
            </small>
          </div>
          <div className="form-field">
            <label htmlFor="scan-type">Type de scan</label>
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
          <button
            className="primary-button"
            type="submit"
            disabled={launch.isPending}
          >
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
      {job && <ScanProgress job={job} onCancel={() => cancel.mutate()} />}
      {job?.status === "succeeded" && (
        <ScanResults job={job} platformId={platformId} onClose={onClose} />
      )}
    </section>
  );
}

function ScanProgress({
  job,
  onCancel,
}: {
  job: ScanJob;
  onCancel: () => void;
}) {
  return (
    <section className="scan-progress" aria-labelledby="scan-progress-title">
      <h2 id="scan-progress-title">Progression</h2>
      <progress max="100" value={job.progress}>
        {job.progress}%
      </progress>
      <p role="status">
        {job.progress}% — {job.current_step}
      </p>
      {job.status === "failed" && (
        <div className="form-error" role="alert">
          {job.sanitized_error ?? "Le scan a échoué."}
        </div>
      )}
      {["queued", "running"].includes(job.status) && (
        <button type="button" onClick={onCancel}>
          Annuler le scan
        </button>
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
  const queryClient = useQueryClient();
  const [items, setItems] = useState<ScanConfirmationItem[]>(() =>
    job.detections.map((item) => ({
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
      await queryClient.invalidateQueries({
        queryKey: ["services", platformId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["categories", platformId, "used"],
      });
    },
  });
  const update = (index: number, changes: Partial<ScanConfirmationItem>) =>
    setItems((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...changes } : item,
      ),
    );
  return (
    <section className="scan-results" aria-labelledby="scan-results-title">
      <h2 id="scan-results-title">Services détectés</h2>
      <p>Corrigez les suggestions avant de les ajouter à l’inventaire.</p>
      <AICategorizationReview
        platformId={platformId}
        items={items
          .filter((item) => item.selected)
          .map((item) => ({
            key: item.detected_service_id,
            name: item.name,
            version: item.version,
          }))}
        disabled={!items.some((item) => item.selected)}
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
      <div className="table-wrapper">
        <table className="service-table">
          <thead>
            <tr>
              <th>Ajouter</th>
              <th>Nom</th>
              <th>Version</th>
              <th>Catégorie</th>
            </tr>
          </thead>
          <tbody>
            {job.detections.map((detection, index) => (
              <tr key={detection.id}>
                <td>
                  <input
                    aria-label={`Ajouter ${detection.detected_name}`}
                    type="checkbox"
                    checked={items[index].selected}
                    onChange={(event) =>
                      update(index, { selected: event.target.checked })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label={`Nom ${detection.detected_name}`}
                    value={items[index].name}
                    onChange={(event) =>
                      update(index, { name: event.target.value })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label={`Version ${detection.detected_name}`}
                    value={items[index].version ?? ""}
                    onChange={(event) =>
                      update(index, { version: event.target.value || null })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label={`Catégorie ${detection.detected_name}`}
                    value={items[index].category ?? ""}
                    placeholder="Non catégorisé"
                    onChange={(event) =>
                      update(index, { category: event.target.value || null })
                    }
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {confirmation.error && (
        <div className="form-error" role="alert">
          La confirmation a échoué.
        </div>
      )}
      {confirmation.data ? (
        <div className="success-message" role="status">
          {confirmation.data.created} service(s) ajouté(s).{" "}
          {onClose ? (
            <button className="link-button" type="button" onClick={onClose}>
              Terminer
            </button>
          ) : (
            <Link to={`/platforms/${platformId}`}>Retour à la plateforme</Link>
          )}
        </div>
      ) : (
        <button
          className="primary-button"
          type="button"
          onClick={() => confirmation.mutate()}
          disabled={confirmation.isPending}
        >
          Confirmer les services sélectionnés
        </button>
      )}
    </section>
  );
}
