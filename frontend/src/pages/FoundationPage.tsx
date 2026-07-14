import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert, LoaderCircle } from "lucide-react";

import { getLiveness } from "../api/health";

export function FoundationPage() {
  const health = useQuery({
    queryKey: ["health", "live"],
    queryFn: ({ signal }) => getLiveness(signal),
  });

  return (
    <main className="foundation-page">
      <section className="foundation-card" aria-labelledby="page-title">
        <div className="logo-placeholder" aria-label="Emplacement du logo MICEPP">
          M
        </div>
        <p className="eyebrow">Socle technique</p>
        <h1 id="page-title">MICEPP-Tracker</h1>
        <p className="intro">
          Le premier sprint prépare une base simple, accessible et prête à recevoir les fonctionnalités
          métier et le futur design Figma.
        </p>

        <div className="status-panel" role="status" aria-live="polite">
          {health.isPending && (
            <>
              <LoaderCircle className="status-icon status-icon--loading" aria-hidden="true" />
              <span>Vérification de l’API…</span>
            </>
          )}
          {health.isSuccess && (
            <>
              <CheckCircle2 className="status-icon" aria-hidden="true" />
              <span>API opérationnelle — version {health.data.version}</span>
            </>
          )}
          {health.isError && (
            <>
              <CircleAlert className="status-icon" aria-hidden="true" />
              <span>L’API ne répond pas encore.</span>
              <button type="button" onClick={() => void health.refetch()}>
                Réessayer
              </button>
            </>
          )}
        </div>

        <ul className="foundation-list" aria-label="Composants du socle">
          <li>Frontend React et TypeScript strict</li>
          <li>API FastAPI avec health checks</li>
          <li>PostgreSQL, Redis et migrations Alembic</li>
          <li>Reverse proxy et environnement Docker Compose</li>
        </ul>
      </section>
    </main>
  );
}

