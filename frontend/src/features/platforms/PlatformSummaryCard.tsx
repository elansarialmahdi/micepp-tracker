import { Hexagon } from "lucide-react";
import { Link } from "react-router";

import type { Platform } from "../../api/platforms";

export function PlatformSummaryCard({ platform, compact = false }: { platform: Platform; compact?: boolean }) {
  const threats = platform.threat_count ?? 0;
  const target = platform.normalized_target
    ? /^(url|ip):/i.test(platform.normalized_target)
      ? platform.normalized_target
      : `${platform.target_type === "ip" ? "Ip" : "Url"}: ${platform.normalized_target}`
    : null;
  return (
    <article className={`platform-summary${compact ? " platform-summary--compact" : ""}${threats > 0 ? " platform-summary--alert" : ""}`}>
      <div className="platform-summary__identity">
        <h2><Link to={`/platforms/${platform.id}`}>{platform.name}</Link></h2>
        {target ? <p>{target}</p> : !compact ? <p>Aucune URL ou adresse IP</p> : null}
      </div>
      <div className="platform-summary__metrics">
        <div><strong>{platform.service_count ?? 0}</strong><span>Services</span></div>
        <div><strong>{threats || "Aucune"}</strong><span>{threats > 1 ? "Menaces" : "Menace"}</span></div>
        <Link
          className="icon-button"
          to={`/platforms/${platform.id}`}
          aria-label={`Ouvrir les paramètres de ${platform.name}`}
          data-tooltip="Voir la plateforme"
          data-tooltip-placement="left"
        >
          <span className="platform-target-icon" aria-hidden="true">
            <Hexagon />
            <span />
          </span>
        </Link>
      </div>
    </article>
  );
}
