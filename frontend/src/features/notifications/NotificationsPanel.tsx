import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bug, EyeOff, Trash2 } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../../api/client";
import {
  getNotifications,
  hideAllNotifications,
  type NotificationItem,
} from "../../api/notifications";
import { useAuth } from "../../auth/AuthProvider";
import {
  notificationServiceLabel,
  ThreatNotificationModal,
} from "../../components/ThreatNotificationModal";

const severityLabels = { critical: "Critique", high: "Élevée", medium: "Moyenne", low: "Faible", info: "Information" };

function severityIcon(severity: string): string {
  return severity === "critical" || severity === "high"
    ? "/assets/wifi-high.svg"
    : "/assets/wifi-low.svg";
}

function relativeTime(value: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "À l’instant";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Il y’a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Il y’a ${hours} h`;
  const days = Math.floor(hours / 24);
  return `Il y’a ${days} j`;
}

export function NotificationsPanel() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [showTrash, setShowTrash] = useState(false);
  const [selectedNotification, setSelectedNotification] = useState<NotificationItem | null>(null);
  const notifications = useQuery({
    queryKey: ["notifications", showTrash],
    queryFn: ({ signal }) => getNotifications(signal, showTrash),
    refetchInterval: 5_000,
    refetchIntervalInBackground: true,
  });
  const hideAll = useMutation({
    mutationFn: hideAllNotifications,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  return (
    <section className="dashboard-panel notification-panel" aria-labelledby="dashboard-notifications-title">
      <div className="section-header">
        <h2 id="dashboard-notifications-title">
          {showTrash ? "Anciennes notifications" : "Notifications"}
        </h2>
        <div className="notification-actions">
          {!showTrash && auth.hasPermission("notification.hide") && Boolean(notifications.data?.items.length) && (
            <button
              className="notification-clear-button panel-icon-button"
              type="button"
              onClick={() => hideAll.mutate()}
              disabled={hideAll.isPending}
              aria-label="Vider les notifications"
              data-tooltip="Vider les notifications"
              data-tooltip-placement="bottom"
            >
              <EyeOff aria-hidden="true" />
            </button>
          )}
          <button
            className="archive-toggle-button panel-icon-button"
            type="button"
            onClick={() => setShowTrash((value) => !value)}
            aria-label={showTrash ? "Retour aux notifications" : "Voir les anciennes notifications"}
            data-tooltip={showTrash ? "Retour aux notifications" : "Anciennes notifications"}
            data-tooltip-placement="bottom"
          >
            {showTrash ? <ArrowLeft aria-hidden="true" /> : <Trash2 aria-hidden="true" />}
          </button>
        </div>
      </div>
      {hideAll.error && <div className="form-error" role="alert">{hideAll.error instanceof ApiError ? hideAll.error.message : "Le masquage a échoué."}</div>}
      {notifications.isPending && <p role="status">Chargement des notifications…</p>}
      {notifications.isError && <div className="form-error" role="alert">Impossible de charger les notifications.</div>}
      {notifications.data?.items.length === 0 && (
        <p className="empty-state">
          {showTrash ? "Aucune ancienne notification." : "Aucune notification visible."}
        </p>
      )}
      <div className="dashboard-scroll notification-feed">
        {notifications.data?.items.map((item) => (
          <button
            className="alert-row alert-row--interactive"
            type="button"
            key={item.id}
            onClick={() => setSelectedNotification(item)}
            aria-label={`Voir les détails de la menace ${notificationServiceLabel(item)}`}
          >
            <span className="alert-row__icon"><Bug aria-hidden="true" /></span>
            <div className="alert-row__body">
              <strong>
                <span className="alert-row__label">Menace</span>{" "}
                {notificationServiceLabel(item)}
              </strong>
              <div className="alert-row__meta">
                <time dateTime={item.created_at}>{relativeTime(item.created_at)}</time>
                <span>plateformes touchées: {item.platform_ids.length}</span>
              </div>
            </div>
            <span
              className={`severity-signal severity-signal--${item.severity}`}
              data-tooltip={`Sévérité : ${severityLabels[item.severity]}`}
              data-tooltip-placement="left"
              aria-label={`Sévérité : ${severityLabels[item.severity]}`}
            >
              <img src={severityIcon(item.severity)} alt="" aria-hidden="true" />
            </span>
          </button>
        ))}
      </div>
      {selectedNotification && (
        <ThreatNotificationModal
          notification={selectedNotification}
          onClose={() => setSelectedNotification(null)}
        />
      )}
    </section>
  );
}
