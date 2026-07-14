import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Filter, Search } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { getPlatforms } from "../api/platforms";
import { PlatformSummaryCard } from "../features/platforms/PlatformSummaryCard";
import { useOutsideClick } from "../hooks/useOutsideClick";

type PlatformFilter = "all" | "threats" | "safe" | "recent";

export function PlatformsPage() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<PlatformFilter>("all");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);
  useOutsideClick(filterRef, filtersOpen, () => setFiltersOpen(false));
  const platforms = useQuery({
    queryKey: ["platforms", "catalog"],
    queryFn: ({ signal }) =>
      getPlatforms({ sort: "-created_at", page: 1, page_size: 100 }, signal),
  });
  const visiblePlatforms = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("fr");
    let items = [...(platforms.data?.items ?? [])];
    if (query)
      items = items.filter((item) =>
        `${item.name} ${item.normalized_target ?? ""}`
          .toLocaleLowerCase("fr")
          .includes(query),
      );
    if (filter === "threats")
      items = items.filter((item) => (item.threat_count ?? 0) > 0);
    if (filter === "safe")
      items = items.filter((item) => (item.threat_count ?? 0) === 0);
    if (filter === "recent")
      items.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    return items;
  }, [filter, platforms.data?.items, search]);

  return (
    <section className="platforms-page" aria-labelledby="platforms-title">
      <div className="page-header platforms-page-header">
        <div className="page-title-block">
          <h1 id="platforms-title">Plateformes</h1>
          <p>Liste de toutes les plateformes ajoutées.</p>
        </div>
        <div className="combined-filter" role="search">
          <div className="search-input combined-search-input">
            <input
              id="platform-search"
              aria-label="Rechercher dans les plateformes"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Rechercher dans les plateformes"
            />
          <div className="custom-dropdown" ref={filterRef}>
            <button
              className="filter-trigger"
              type="button"
              aria-expanded={filtersOpen}
              onClick={() => setFiltersOpen((open) => !open)}
            >
              <Filter aria-hidden="true" />
              <span>Filtrer par</span>
              <ChevronDown aria-hidden="true" />
            </button>
            {filtersOpen && (
              <div className="custom-dropdown__menu" role="menu">
                {(
                  [
                    ["all", "Toutes les plateformes"],
                    ["threats", "Avec au moins une menace"],
                    ["safe", "Sans menace"],
                    ["recent", "Dernières ajoutées"],
                  ] as [PlatformFilter, string][]
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    role="menuitemradio"
                    aria-checked={filter === value}
                    onClick={() => {
                      setFilter(value);
                      setFiltersOpen(false);
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <Search aria-hidden="true" />
          </div>
        </div>
      </div>
      {platforms.isPending && <p role="status">Chargement des plateformes…</p>}
      {platforms.isError && (
        <div className="form-error" role="alert">
          {platforms.error instanceof ApiError
            ? platforms.error.message
            : "Impossible de charger les plateformes."}
        </div>
      )}
      <div
        className="platform-grid platform-grid--three"
        aria-label="Liste des plateformes"
      >
        {visiblePlatforms.map((platform) => (
          <PlatformSummaryCard key={platform.id} platform={platform} />
        ))}
      </div>
      {!platforms.isPending && visiblePlatforms.length === 0 && (
        <p className="empty-state">
          Aucune plateforme ne correspond à la recherche.
        </p>
      )}
    </section>
  );
}
