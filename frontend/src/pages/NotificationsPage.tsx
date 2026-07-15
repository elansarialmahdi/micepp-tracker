import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, EyeOff } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../api/client";
import {
  getNotifications,
  hideAllNotifications,
  hideNotification,
  readNotification,
  type NotificationItem,
} from "../api/notifications";
import { useAuth } from "../auth/AuthProvider";
import {
  notificationServiceLabel,
  ThreatNotificationModal,
} from "../components/ThreatNotificationModal";

const severityLabels = {
  critical: "Critique",
  high: "Élevée",
  medium: "Moyenne",
  low: "Faible",
  info: "Information",
};

export function NotificationsPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [selectedNotification, setSelectedNotification] = useState<NotificationItem | null>(null);
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: ({ signal }) => getNotifications(signal),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });
  const read = useMutation({ mutationFn: readNotification, onSuccess: refresh });
  const hide = useMutation({ mutationFn: hideNotification, onSuccess: refresh });
  const hideAll = useMutation({ mutationFn: hideAllNotifications, onSuccess: refresh });
  const mutationError = read.error ?? hide.error ?? hideAll.error;

  return (
    <section aria-labelledby="notifications-title">
      <div className="page-header">
        <div>
          <p className="eyebrow">Centre d’alertes</p>
          <h1 id="notifications-title">Notifications</h1>
        </div>
        {auth.hasPermission("notification.hide") && Boolean(notifications.data?.items.length) && (
          <button type="button" onClick={() => hideAll.mutate()} disabled={hideAll.isPending}>
            <EyeOff aria-hidden="true" /> Tout masquer
          </button>
        )}
      </div>
      {mutationError && (
        <div className="form-error" role="alert">
          {mutationError instanceof ApiError ? mutationError.message : "L’action a échoué."}
        </div>
      )}
      {notifications.isPending && <p role="status">Chargement des notifications…</p>}
      {notifications.isError && (
        <div className="form-error" role="alert">Impossible de charger les notifications.</div>
      )}
      {notifications.data?.items.length === 0 && <p>Aucune notification visible.</p>}
      <div className="notification-list">
        {notifications.data?.items.map((item) => (
          <article
            className={`notification-item notification-item--${item.severity}${item.is_read ? " notification-item--read" : ""}`}
            key={item.id}
          >
            <button
              className="notification-item__open"
              type="button"
              onClick={() => setSelectedNotification(item)}
              aria-label={`Voir les détails de la menace ${notificationServiceLabel(item)}`}
            >
              <span className="severity-label">{severityLabels[item.severity]}</span>
              <h2>Menace {notificationServiceLabel(item)}</h2>
              <p>{item.message}</p>
              <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString("fr-FR")}</time>
            </button>
            <div className="notification-actions">
              {!item.is_read && (
                <button type="button" onClick={() => read.mutate(item.id)} disabled={read.isPending}>
                  <Check aria-hidden="true" /> Marquer comme lue
                </button>
              )}
              {auth.hasPermission("notification.hide") && (
                <button type="button" onClick={() => hide.mutate(item.id)} disabled={hide.isPending}>
                  <EyeOff aria-hidden="true" /> Masquer
                </button>
              )}
            </div>
          </article>
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
