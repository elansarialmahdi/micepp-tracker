import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RefreshCw, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import {
  getCurrentProtectionJob,
  getRealtimeSettings,
  runRealtimeProtection,
  updateRealtimeSettings,
  type ProtectionJob,
} from "../../api/realtime";
import { useAuth } from "../../auth/AuthProvider";
import { CustomSelect } from "../../components/CustomSelect";
import { ModalPortal } from "../../components/ModalPortal";
import { ToggleSwitch } from "../../components/ToggleSwitch";

type IntervalUnit = "minutes" | "hours" | "days";
const unitSeconds: Record<IntervalUnit, number> = {
  minutes: 60,
  hours: 3600,
  days: 86400,
};

export function countdown(
  nextRunAt: string | null,
  now = Date.now(),
): string | null {
  if (!nextRunAt) return null;
  const remaining = Math.max(
    0,
    Math.ceil((new Date(nextRunAt).getTime() - now) / 1000),
  );
  if (remaining === 0) return "quelques instants";
  const days = Math.floor(remaining / 86400);
  const hours = Math.floor((remaining % 86400) / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  const seconds = remaining % 60;
  if (!days && !hours) {
    return `${String(minutes).padStart(2, "0")} min ${seconds} s`;
  }
  return [
    days && `${days} j`,
    hours && `${hours} h`,
    minutes && `${minutes} min`,
    `${seconds} s`,
  ]
    .filter(Boolean)
    .join(" ");
}

export function isActiveProtectionJob(
  job: ProtectionJob | null | undefined,
  now = Date.now(),
): job is ProtectionJob {
  if (!job || !["queued", "running"].includes(job.status)) return false;
  const activity = job.heartbeat_at ?? job.started_at ?? job.created_at;
  if (!activity) return true;
  const activityTime = Date.parse(activity);
  if (Number.isNaN(activityTime)) return false;
  const staleAfter = job.status === "queued" ? 120_000 : 180_000;
  return now - activityTime <= staleAfter;
}

export function RealtimeProtectionCard() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [now, setNow] = useState(Date.now());
  const [configuring, setConfiguring] = useState(false);
  const [value, setValue] = useState(1);
  const [unit, setUnit] = useState<IntervalUnit>("hours");
  const settings = useQuery({
    queryKey: ["realtime-settings"],
    queryFn: ({ signal }) => getRealtimeSettings(signal),
  });
  const job = useQuery({
    queryKey: ["realtime-job"],
    queryFn: ({ signal }) => getCurrentProtectionJob(signal),
    refetchOnMount: "always",
    refetchInterval: (query) => {
      const status = query.state.data?.status ?? "";
      if (["queued", "running"].includes(status)) return 400;
      return settings.data?.enabled ? 1000 : 10000;
    },
  });
  const reload = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["realtime-settings"] }),
      queryClient.invalidateQueries({ queryKey: ["realtime-job"] }),
    ]);
  };
  const update = useMutation({
    mutationFn: updateRealtimeSettings,
    onSuccess: reload,
  });
  const run = useMutation({
    mutationFn: runRealtimeProtection,
    onSuccess: async (newJob) => {
      queryClient.setQueryData(["realtime-job"], newJob);
      await reload();
    },
  });

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    const status = job.data?.status;
    if (status && !["queued", "running"].includes(status)) {
      void settings.refetch();
    }
  }, [job.data?.id, job.data?.status]);
  const remaining = useMemo(
    () => countdown(settings.data?.next_run_at ?? null, now),
    [settings.data?.next_run_at, now],
  );
  const scheduledStarting =
    settings.data?.enabled &&
    job.isFetchedAfterMount &&
    remaining === "quelques instants";
  const activeJob =
    job.isFetchedAfterMount &&
    isActiveProtectionJob(job.data, now)
      ? job.data
      : null;
  const progress = activeJob?.total_services
    ? Math.round(
        (activeJob.processed_services / activeJob.total_services) * 100,
      )
    : 0;
  const currentServices = activeJob?.current_service_names?.length
    ? `${activeJob.current_service_names.slice(0, 2).join(", ")}${activeJob.current_service_names.length > 2 ? ` +${activeJob.current_service_names.length - 2}` : ""}`
    : null;

  function openConfiguration() {
    const seconds = settings.data?.interval_seconds ?? 3600;
    if (seconds % 86400 === 0) {
      setUnit("days");
      setValue(seconds / 86400);
    } else if (seconds % 3600 === 0) {
      setUnit("hours");
      setValue(seconds / 3600);
    } else {
      setUnit("minutes");
      setValue(Math.max(1, Math.round(seconds / 60)));
    }
    setConfiguring(true);
  }

  if (settings.isPending)
    return (
      <section className="realtime-card">
        <p role="status">Chargement de la protection…</p>
      </section>
    );
  if (settings.isError || !settings.data)
    return (
      <section className="realtime-card">
        <div className="form-error" role="alert">
          Impossible de charger la protection périodique.
        </div>
        <button onClick={() => settings.refetch()}>Réessayer</button>
      </section>
    );

  return (
    <section
      className={`realtime-card ${settings.data.enabled ? "realtime-card--enabled" : ""}`}
      aria-labelledby="realtime-title"
    >
      <div className="realtime-card__title">
        <ToggleSwitch
          className="realtime-card__toggle"
          checked={settings.data.enabled}
          disabled={
            update.isPending || !auth.hasPermission("settings.update")
          }
          aria-label="Activer la protection en temps réel"
          onChange={(event) =>
            update.mutate({ enabled: event.target.checked })
          }
        />
        <div>
          <h2 id="realtime-title">
            Protection en temps réel{" "}
            <strong className="realtime-card__state">
              {settings.data.enabled ? "activée" : "désactivée"}
            </strong>
          </h2>
          {activeJob ? (
            <span className="realtime-inline-progress" aria-live="polite">
              <span>{currentServices ? `Vérification de ${currentServices} :` : "Vérification des services :"}</span>
              <strong>{activeJob.processed_services}/{activeJob.total_services}</strong>
              <progress max="100" value={progress} aria-label={`Vérification à ${progress} %`} />
            </span>
          ) : run.isPending ? (
            <span
              className="realtime-inline-progress realtime-inline-progress--pending"
              aria-live="polite"
            >
              <span>Vérification des services :</span>
              <strong>0/{job.data?.total_services || "…"}</strong>
              <progress aria-label="Démarrage de la vérification" />
            </span>
          ) : scheduledStarting ? (
            <span
              className="realtime-inline-progress realtime-inline-progress--pending"
              aria-live="polite"
            >
              <span>Démarrage de la vérification :</span>
              <progress aria-label="Démarrage de la vérification" />
            </span>
          ) : settings.data.enabled && remaining ? (
            <p>, vérification de tous les services dans: <strong>{remaining}</strong></p>
          ) : null}
        </div>
      </div>
      {(update.error || run.error) && (
        <div className="form-error" role="alert">
          {(update.error ?? run.error) instanceof ApiError
            ? (update.error ?? run.error)?.message
            : "L’opération a échoué."}
        </div>
      )}
      <div className="form-actions">
        {auth.hasPermission("settings.update") &&
          !activeJob &&
          !scheduledStarting &&
          !run.isPending && (
          <button
            className="realtime-refresh-button"
            type="button"
            onClick={() => run.mutate()}
            aria-label="Actualiser la protection"
            data-tooltip="Vérifier maintenant"
          >
            <RefreshCw aria-hidden="true" />
          </button>
          )}
          {auth.hasPermission("settings.update") && settings.data.enabled && (
            <button type="button" onClick={openConfiguration}>
              <img className="settings-icon realtime-settings-icon" src="/assets/settings-icon.svg" alt="" aria-hidden="true" />
              Configurer
            </button>
          )}
          {auth.hasPermission("settings.update") && !activeJob && (
            <button
              className="primary-button"
              type="button"
              disabled={run.isPending}
              onClick={() => run.mutate()}
            >
              <Play aria-hidden="true" />
              {run.isPending ? "Lancement…" : "Vérifier maintenant"}
            </button>
          )}
        </div>
      {configuring && (
        <ModalPortal>
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setConfiguring(false);
            }}
          >
            <div
              className="settings-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="interval-title"
            >
              <div className="section-header">
                <h3 id="interval-title">Intervalle de vérification</h3>
                <button
                  aria-label="Fermer"
                  data-tooltip="Fermer"
                  data-tooltip-placement="bottom"
                  onClick={() => setConfiguring(false)}
                >
                  <X aria-hidden="true" />
                </button>
              </div>
              <div className="interval-fields">
                <div className="form-field">
                  <label htmlFor="interval-value">Valeur</label>
                  <input
                    id="interval-value"
                    type="number"
                    min="1"
                    value={value}
                    onChange={(event) =>
                      setValue(Math.max(1, Number(event.target.value)))
                    }
                  />
                </div>
                <div className="form-field">
                  <label htmlFor="interval-unit">Unité</label>
                  <CustomSelect
                    id="interval-unit"
                    value={unit}
                    onChange={(next) => setUnit(next as IntervalUnit)}
                    options={[
                      { value: "minutes", label: "Minutes" },
                      { value: "hours", label: "Heures" },
                      { value: "days", label: "Jours" },
                    ]}
                  />
                </div>
              </div>
              <p className="password-hint">
                Minimum serveur :{" "}
                {Math.ceil(settings.data.min_interval_seconds / 60)} minute(s).
              </p>
              <div className="form-actions">
                <button onClick={() => setConfiguring(false)}>Annuler</button>
                <button
                  className="primary-button"
                  disabled={
                    update.isPending ||
                    value * unitSeconds[unit] < settings.data.min_interval_seconds
                  }
                  onClick={() =>
                    update.mutate(
                      { interval_seconds: value * unitSeconds[unit] },
                      { onSuccess: () => setConfiguring(false) },
                    )
                  }
                >
                  Enregistrer
                </button>
              </div>
            </div>
          </div>
        </ModalPortal>
      )}
    </section>
  );
}
