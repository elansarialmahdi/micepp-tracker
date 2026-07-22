import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Clock3,
  Eye,
  FileClock,
  Globe2,
  Monitor,
  Search,
  ShieldAlert,
  Trash2,
  UserRound,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  clearActivityHistory,
  getActivityHistory,
  type ActivityResult,
  type AuditEvent,
} from "../api/history";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { CustomSelect } from "../components/CustomSelect";

const resultOptions = [
  { value: "all", label: "Tous les résultats" },
  { value: "success", label: "Actions réussies" },
  { value: "failure", label: "Échecs et refus" },
];

function metadataText(event: AuditEvent, key: string): string | null {
  const value = event.metadata[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : null;
}

function isFailure(event: AuditEvent): boolean {
  return (
    metadataText(event, "result") === "failure" ||
    event.action.endsWith(".failed") ||
    event.action.endsWith(".failure") ||
    event.action.includes("denied")
  );
}

function eventActor(event: AuditEvent): string {
  return event.actor_name ?? metadataText(event, "username") ?? "Système / visiteur";
}

function eventIcon(event: AuditEvent) {
  if (isFailure(event)) return ShieldAlert;
  if (event.action === "page.view") return Eye;
  if (event.action.startsWith("auth.")) return UserRound;
  return Activity;
}

function hasDetails(event: AuditEvent): boolean {
  return Boolean(
    event.before_data ||
      event.after_data ||
      Object.keys(event.metadata).length ||
      event.request_id,
  );
}

function EventDetails({ event }: { event: AuditEvent }) {
  if (!hasDetails(event)) return null;
  return (
    <details className="activity-event__details">
      <summary>Voir les détails techniques</summary>
      <dl>
        <div>
          <dt>Action</dt>
          <dd>{event.action}</dd>
        </div>
        <div>
          <dt>Type d’objet</dt>
          <dd>{event.entity_type}</dd>
        </div>
        {event.entity_id && (
          <div>
            <dt>Identifiant de l’objet</dt>
            <dd>{event.entity_id}</dd>
          </div>
        )}
        {event.request_id && (
          <div>
            <dt>Identifiant de requête</dt>
            <dd>{event.request_id}</dd>
          </div>
        )}
      </dl>
      {event.before_data && (
        <div className="activity-event__json">
          <strong>Avant</strong>
          <pre>{JSON.stringify(event.before_data, null, 2)}</pre>
        </div>
      )}
      {event.after_data && (
        <div className="activity-event__json">
          <strong>Après</strong>
          <pre>{JSON.stringify(event.after_data, null, 2)}</pre>
        </div>
      )}
      {Object.keys(event.metadata).length > 0 && (
        <div className="activity-event__json">
          <strong>Métadonnées</strong>
          <pre>{JSON.stringify(event.metadata, null, 2)}</pre>
        </div>
      )}
    </details>
  );
}

export function ActivityPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [result, setResult] = useState<ActivityResult>("all");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const history = useQuery({
    queryKey: ["activity-history", debouncedSearch, result, page],
    queryFn: ({ signal }) =>
      getActivityHistory({ q: debouncedSearch, result, page, pageSize: 50 }, signal),
    refetchInterval: 5_000,
    refetchIntervalInBackground: true,
    placeholderData: (previous) => previous,
  });
  const clearing = useMutation({
    mutationFn: clearActivityHistory,
    onSuccess: async () => {
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["activity-history"] });
    },
  });

  function clearLogs() {
    if (
      window.confirm(
        "Masquer tous les logs actuellement affichés ? Les événements resteront conservés dans la base.",
      )
    ) {
      clearing.mutate();
    }
  }

  const data = history.data;
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / (data?.page_size ?? 50)));
  const allResults = (data?.success_total ?? 0) + (data?.failure_total ?? 0);

  return (
    <section className="activity-page" aria-labelledby="activity-title">
      <div className="page-header activity-page__header">
        <div>
          <p className="eyebrow">Audit & sécurité</p>
          <h1 id="activity-title">Historique des activités</h1>
          <p className="activity-page__intro">
            Suivi détaillé des connexions, consultations, modifications et tentatives échouées.
          </p>
        </div>
        <div className="activity-page__actions">
          {auth.hasPermission("history.clear") && (
            <button
              className="activity-clear-button"
              type="button"
              disabled={clearing.isPending}
              onClick={clearLogs}
            >
              <Trash2 aria-hidden="true" />
              {clearing.isPending ? "Effacement…" : "Effacer les logs"}
            </button>
          )}
          <span className="activity-live" role="status">
            <span aria-hidden="true" /> Actualisation toutes les 5 secondes
          </span>
        </div>
      </div>

      {clearing.isError && (
        <div className="form-error activity-state" role="alert">
          {clearing.error instanceof ApiError
            ? clearing.error.message
            : "Impossible d’effacer les logs."}
        </div>
      )}

      <div className="activity-stats" aria-label="Résumé de l’activité">
        <article>
          <FileClock aria-hidden="true" />
          <div><span>Événements</span><strong>{allResults}</strong></div>
        </article>
        <article className="activity-stat--success">
          <CircleCheck aria-hidden="true" />
          <div><span>Réussites</span><strong>{data?.success_total ?? 0}</strong></div>
        </article>
        <article className="activity-stat--failure">
          <AlertTriangle aria-hidden="true" />
          <div><span>Échecs et refus</span><strong>{data?.failure_total ?? 0}</strong></div>
        </article>
      </div>

      <div className="activity-filters">
        <label className="search-input activity-search">
          <Search aria-hidden="true" />
          <span className="sr-only">Rechercher dans l’historique</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Utilisateur, IP, action ou événement…"
          />
        </label>
        <CustomSelect
          value={result}
          options={resultOptions}
          ariaLabel="Filtrer par résultat"
          onChange={(value) => {
            setResult(value as ActivityResult);
            setPage(1);
          }}
          className="activity-result-select"
        />
      </div>

      {history.isPending && <p className="activity-state" role="status">Chargement de l’historique…</p>}
      {history.isError && (
        <div className="form-error activity-state" role="alert">
          Impossible de charger l’historique des activités.
        </div>
      )}
      {data?.items.length === 0 && !history.isError && (
        <div className="activity-empty">
          <Clock3 aria-hidden="true" />
          <h2>Aucun événement trouvé</h2>
          <p>Modifiez les filtres pour élargir la recherche.</p>
        </div>
      )}

      {Boolean(data?.items.length) && (
        <div className="activity-feed">
          {data?.items.map((event) => {
            const Icon = eventIcon(event);
            const failed = isFailure(event);
            const browser = metadataText(event, "browser");
            return (
              <article
                className={`activity-event${failed ? " activity-event--failure" : ""}`}
                key={event.id}
              >
                <span className="activity-event__icon"><Icon aria-hidden="true" /></span>
                <div className="activity-event__content">
                  <div className="activity-event__heading">
                    <div>
                      <span className={`activity-result activity-result--${failed ? "failure" : "success"}`}>
                        {failed ? "Échec" : "Réussite"}
                      </span>
                      <h2>{event.summary}</h2>
                    </div>
                    <time dateTime={event.created_at}>
                      {new Date(event.created_at).toLocaleString("fr-FR", {
                        dateStyle: "medium",
                        timeStyle: "medium",
                      })}
                    </time>
                  </div>
                  <div className="activity-event__meta">
                    <span><UserRound aria-hidden="true" /> {eventActor(event)}</span>
                    <span><Globe2 aria-hidden="true" /> {event.ip ?? "IP non disponible"}</span>
                    <span><Monitor aria-hidden="true" /> {browser ?? "Client non renseigné"}</span>
                  </div>
                  <EventDetails event={event} />
                </div>
              </article>
            );
          })}
        </div>
      )}

      {data && data.total > data.page_size && (
        <nav className="activity-pagination" aria-label="Pagination de l’historique">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            <ChevronLeft aria-hidden="true" /> Précédent
          </button>
          <span>Page {page} sur {totalPages}</span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
          >
            Suivant <ChevronRight aria-hidden="true" />
          </button>
        </nav>
      )}
    </section>
  );
}
