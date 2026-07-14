import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bug, EyeOff, Signal } from "lucide-react";

import { ApiError } from "../../api/client";
import { getNotifications, hideAllNotifications } from "../../api/notifications";
import { useAuth } from "../../auth/AuthProvider";

const severityLabels = { critical: "Critique", high: "Élevée", medium: "Moyenne", low: "Faible", info: "Information" };

function relativeTime(value: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "À l’instant";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Il y a ${minutes} minute${minutes > 1 ? "s" : ""}`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Il y a ${hours} heure${hours > 1 ? "s" : ""}`;
  const days = Math.floor(hours / 24);
  return `Il y a ${days} jour${days > 1 ? "s" : ""}`;
}

export function NotificationsPanel() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const notifications = useQuery({ queryKey: ["notifications"], queryFn: ({ signal }) => getNotifications(signal) });
  const hideAll = useMutation({
    mutationFn: hideAllNotifications,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  return (
    <section className="dashboard-panel notification-panel" aria-labelledby="dashboard-notifications-title">
      <div className="section-header">
        <h2 id="dashboard-notifications-title">Notifications</h2>
        {auth.hasPermission("notification.hide") && Boolean(notifications.data?.items.length) && (
          <button type="button" onClick={() => hideAll.mutate()} disabled={hideAll.isPending}>
            <EyeOff aria-hidden="true" /> Vider les notifications
          </button>
        )}
      </div>
      {hideAll.error && <div className="form-error" role="alert">{hideAll.error instanceof ApiError ? hideAll.error.message : "Le masquage a échoué."}</div>}
      {notifications.isPending && <p role="status">Chargement des notifications…</p>}
      {notifications.isError && <div className="form-error" role="alert">Impossible de charger les notifications.</div>}
      {notifications.data?.items.length === 0 && <p className="empty-state">Aucune notification visible.</p>}
      <div className="dashboard-scroll notification-feed">
        {notifications.data?.items.map((item) => (
          <article className="alert-row" key={item.id}>
            <span className="alert-row__icon"><Bug aria-hidden="true" /></span>
            <div className="alert-row__body">
              <strong><span className="alert-row__label">Menace</span> {item.title}</strong>
              <div className="alert-row__meta">
                <time dateTime={item.created_at}>{relativeTime(item.created_at)}</time>
                <span>{item.platform_ids.length} plateforme{item.platform_ids.length > 1 ? "s" : ""} touchée{item.platform_ids.length > 1 ? "s" : ""}</span>
              </div>
            </div>
            <span className={`severity-signal severity-signal--${item.severity}`} title={`Sévérité : ${severityLabels[item.severity]}`} aria-label={`Sévérité : ${severityLabels[item.severity]}`}>
              <Signal aria-hidden="true" />
            </span>
          </article>
        ))}
      </div>
    </section>
  );
}
