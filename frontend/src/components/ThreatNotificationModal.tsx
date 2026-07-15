import { Bug, ChevronRight, Server, X } from "lucide-react";
import { Link } from "react-router";

import type { NotificationItem } from "../api/notifications";
import { ModalPortal } from "./ModalPortal";

const severityLabels = {
  critical: "Critique",
  high: "Élevée",
  medium: "Moyenne",
  low: "Faible",
  info: "Information",
};

export function notificationServiceLabel(item: NotificationItem): string {
  const service = item.service_name?.trim();
  if (!service) return item.title;
  return [service, item.service_version?.trim()].filter(Boolean).join(" ");
}

type ThreatNotificationModalProps = {
  notification: NotificationItem;
  onClose: () => void;
};

export function ThreatNotificationModal({ notification, onClose }: ThreatNotificationModalProps) {
  return (
    <ModalPortal>
      <div
        className="modal-backdrop"
        role="presentation"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      >
        <section
          className="settings-modal threat-notification-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="threat-notification-title"
        >
          <header className="settings-modal__header">
            <div className="threat-notification-modal__title">
              <span className="threat-notification-modal__icon" aria-hidden="true">
                <Bug />
              </span>
              <div>
                <p className="eyebrow">Détails de la menace</p>
                <h2 id="threat-notification-title">
                  Menace {notificationServiceLabel(notification)}
                </h2>
              </div>
            </div>
            <button
              className="panel-icon-button"
              type="button"
              onClick={onClose}
              aria-label="Fermer"
              data-tooltip="Fermer"
              data-tooltip-placement="left"
            >
              <X aria-hidden="true" />
            </button>
          </header>

          <div className="threat-notification-modal__body">
            <div className="threat-notification-modal__summary">
              <span className={`severity-badge severity-badge--${notification.severity}`}>
                {severityLabels[notification.severity]}
              </span>
              <p>{notification.message}</p>
            </div>

            <dl className="threat-notification-modal__details">
              <div>
                <dt>Service</dt>
                <dd>{notification.service_name ?? "Non renseigné"}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{notification.service_version ?? "Non renseignée"}</dd>
              </div>
              <div>
                <dt>Identifiant</dt>
                <dd>{notification.threat_identifier ?? "Non renseigné"}</dd>
              </div>
              <div>
                <dt>Détectée le</dt>
                <dd>{new Date(notification.created_at).toLocaleString("fr-FR")}</dd>
              </div>
            </dl>

            <div className="threat-notification-modal__platforms">
              <div className="threat-notification-modal__section-heading">
                <h3>Plateformes concernées</h3>
                <span>{notification.platforms.length}</span>
              </div>
              {notification.platforms.length === 0 ? (
                <p className="empty-state">Aucune plateforme associée.</p>
              ) : (
                <ul>
                  {notification.platforms.map((platform) => (
                    <li key={platform.id}>
                      <Link to={`/platforms/${platform.id}`} onClick={onClose}>
                        <Server aria-hidden="true" />
                        <span>{platform.name}</span>
                        <ChevronRight aria-hidden="true" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </section>
      </div>
    </ModalPortal>
  );
}
