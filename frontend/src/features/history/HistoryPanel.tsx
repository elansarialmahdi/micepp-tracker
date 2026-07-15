import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  EyeOff,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import { getPlatformHistory, hidePlatformHistory } from "../../api/history";
import { useAuth } from "../../auth/AuthProvider";

function EventIcon({ action }: { action: string }) {
  action = action ?? "";
  if (action.includes("archive") || action.includes("delete"))
    return <Trash2 aria-hidden="true" />;
  if (action.includes("update") || action.includes("upgrade"))
    return <RefreshCw aria-hidden="true" />;
  if (action.includes("create")) return <Plus aria-hidden="true" />;
  return <Pencil aria-hidden="true" />;
}

function userFacingSummary(summary: string): string {
  return summary
    .replace("Plateforme archivée", "Plateforme supprimée")
    .replace("Catégorie archivée", "Catégorie supprimée")
    .replace("Service archivé", "Service supprimé");
}

export function HistoryPanel({ platformId }: { platformId: string }) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [showTrash, setShowTrash] = useState(false);
  const history = useQuery({
    queryKey: ["platform-history", platformId, showTrash],
    queryFn: ({ signal }) => getPlatformHistory(platformId, signal, showTrash),
  });
  const hide = useMutation({
    mutationFn: () => hidePlatformHistory(platformId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["platform-history", platformId],
      }),
  });

  return (
    <section className="history-panel" aria-labelledby="history-title">
      <div className="section-header">
        <h2 id="history-title">
          {showTrash ? "Ancien historique" : "Historique"}
        </h2>
        <div className="history-actions">
          {!showTrash &&
            auth.hasPermission("history.hide") &&
            Boolean(history.data?.items.length) && (
              <button
                className="history-clear-button panel-icon-button"
                type="button"
                onClick={() => hide.mutate()}
                disabled={hide.isPending}
                aria-label="Vider l’historique"
                data-tooltip="Vider l’historique"
                data-tooltip-placement="bottom"
              >
                <EyeOff aria-hidden="true" />
              </button>
            )}
          {showTrash ? (
            <button
              className="archive-toggle-button panel-icon-button"
              type="button"
              onClick={() => setShowTrash(false)}
              aria-label="Retour"
              data-tooltip="Retour à l’historique"
              data-tooltip-placement="bottom"
            >
              <ArrowLeft aria-hidden="true" />
            </button>
          ) : (
            <button
              className="archive-toggle-button panel-icon-button"
              type="button"
              aria-label="Voir l’ancien historique"
              data-tooltip="Ancien historique"
              data-tooltip-placement="bottom"
              onClick={() => setShowTrash(true)}
            >
              <Trash2 aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
      {hide.error && (
        <div className="form-error" role="alert">
          Le masquage a échoué.
        </div>
      )}
      {history.isPending && <p role="status">Chargement de l’historique…</p>}
      {history.isError && (
        <div className="form-error" role="alert">
          Impossible de charger l’historique.
        </div>
      )}
      {history.data?.items.length === 0 && (
        <p className="empty-state">
          {showTrash ? "Aucun ancien historique." : "Aucune action visible."}
        </p>
      )}
      <ol className="history-list dashboard-scroll">
        {history.data?.items.map((event) => (
          <li key={event.id}>
            <span className="history-icon">
              <EventIcon action={event.action} />
            </span>
            <span>
              <strong>{userFacingSummary(event.summary)}</strong>
              <small>
                <time dateTime={event.created_at}>
                  {new Date(event.created_at).toLocaleString("fr-FR")}
                </time>
                {event.actor_name
                  ? ` · par ${event.actor_name}`
                  : " · action système"}
              </small>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
