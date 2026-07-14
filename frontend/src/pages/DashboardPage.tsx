import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { getPlatforms } from "../api/platforms";
import { useAuth } from "../auth/AuthProvider";
import { NotificationsPanel } from "../features/notifications/NotificationsPanel";
import { PlatformSummaryCard } from "../features/platforms/PlatformSummaryCard";
import { RealtimeProtectionCard } from "../features/realtime/RealtimeProtectionCard";

export function DashboardPage() {
  const auth = useAuth();
  const [search, setSearch] = useState("");
  const platforms = useQuery({
    queryKey: ["platforms", "dashboard"],
    queryFn: ({ signal }) => getPlatforms({ sort: "-created_at", page: 1, page_size: 100 }, signal),
  });
  const visiblePlatforms = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("fr");
    if (!query) return platforms.data?.items ?? [];
    return (platforms.data?.items ?? []).filter((platform) =>
      `${platform.name} ${platform.normalized_target ?? ""}`.toLocaleLowerCase("fr").includes(query),
    );
  }, [platforms.data?.items, search]);

  return (
    <section className="dashboard-page" aria-labelledby="dashboard-title">
      <header className="page-title-block">
        <h1 id="dashboard-title">Tableau de bord</h1>
        <p>L’espace dédié à l’observation des nouvelles alertes.</p>
      </header>
      <div className="dashboard-columns">
        <section className="dashboard-panel platform-panel" aria-labelledby="dashboard-platforms-title">
          <h2 id="dashboard-platforms-title" className="sr-only">Plateformes</h2>
          <label className="search-input" htmlFor="dashboard-platform-search">
            <Search aria-hidden="true" />
            <input
              id="dashboard-platform-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Rechercher dans les plateformes"
            />
          </label>
          {platforms.isPending && <p role="status">Chargement des plateformes…</p>}
          {platforms.isError && <div className="form-error" role="alert">Impossible de charger les plateformes.</div>}
          <div className="dashboard-scroll platform-feed">
            {visiblePlatforms.map((platform) => <PlatformSummaryCard key={platform.id} platform={platform} compact />)}
            {!platforms.isPending && visiblePlatforms.length === 0 && <p className="empty-state">Aucune plateforme trouvée.</p>}
          </div>
        </section>
        {auth.hasPermission("notification.read") ? <NotificationsPanel /> : (
          <section className="dashboard-panel"><h2>Notifications</h2><p>Vous n’avez pas accès aux notifications.</p></section>
        )}
      </div>
      <RealtimeProtectionCard />
    </section>
  );
}
