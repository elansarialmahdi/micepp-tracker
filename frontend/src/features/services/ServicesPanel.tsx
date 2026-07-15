import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Filter,
  FolderPlus,
  MoreHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router";

import { ApiError } from "../../api/client";
import {
  archiveCategory,
  archiveService,
  createCategory,
  getCategories,
  getServices,
  updateService,
  type Category,
  type Service,
  type ServiceInput,
} from "../../api/inventory";
import { useAuth } from "../../auth/AuthProvider";
import { CustomSelect } from "../../components/CustomSelect";
import { ModalPortal } from "../../components/ModalPortal";
import { ViewportMenuPortal } from "../../components/ViewportMenuPortal";

function ServiceEditModal({
  service,
  categories,
  onClose,
  onSaved,
}: {
  service: Service;
  categories: Category[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { control, register, handleSubmit, formState } = useForm({
    defaultValues: {
      name: service.name,
      version: service.version ?? "",
      category_id: service.category_id ?? "",
    },
  });
  const mutation = useMutation({
    mutationFn: (input: ServiceInput) => updateService(service.id, input),
  });
  const submit = handleSubmit(async (values) => {
    await mutation.mutateAsync({
      name: values.name.trim(),
      version: values.version.trim() || null,
      category_id: values.category_id || null,
    });
    await onSaved();
    onClose();
  });
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
          className="settings-modal service-edit-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="service-edit-title"
        >
          <div className="section-header">
            <h2 id="service-edit-title">Modifier {service.name}</h2>
            <button
              type="button"
              aria-label="Fermer"
              data-tooltip="Fermer"
              data-tooltip-placement="bottom"
              onClick={onClose}
            >
              <X aria-hidden="true" />
            </button>
          </div>
          <form className="platform-form" onSubmit={submit}>
          <div className="form-field">
            <label htmlFor="modal-service-name">Nom</label>
            <input
              id="modal-service-name"
              {...register("name", { required: true })}
            />
            {formState.errors.name && (
              <p className="field-error">Le nom est obligatoire.</p>
            )}
          </div>
          <div className="form-field">
            <label htmlFor="modal-service-version">Version</label>
            <input id="modal-service-version" {...register("version")} />
          </div>
          <div className="form-field">
            <label htmlFor="modal-service-category">Catégorie</label>
            <Controller
              control={control}
              name="category_id"
              render={({ field }) => (
                <CustomSelect
                  id="modal-service-category"
                  value={field.value}
                  onChange={field.onChange}
                  options={[
                    { value: "", label: "Non catégorisé" },
                    ...categories.map((item) => ({ value: item.id, label: item.name })),
                  ]}
                />
              )}
            />
          </div>
          {mutation.error && (
            <div className="form-error" role="alert">
              {mutation.error instanceof ApiError
                ? mutation.error.message
                : "La modification a échoué."}
            </div>
          )}
          <div className="form-actions">
            <button type="button" onClick={onClose}>
              Annuler
            </button>
            <button
              className="primary-button"
              type="submit"
              disabled={mutation.isPending}
            >
              Enregistrer
            </button>
          </div>
          </form>
        </section>
      </div>
    </ModalPortal>
  );
}

export function ServicesPanel({
  platformId,
  archived,
  categoriesOpen,
  onToggleCategories,
}: {
  platformId: string;
  archived: boolean;
  categoriesOpen?: boolean;
  onToggleCategories?: () => void;
}) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("service_q") ?? "");
  const [internalCategoriesOpen, setInternalCategoriesOpen] = useState(false);
  const showCategories = categoriesOpen ?? internalCategoriesOpen;
  const [categoryName, setCategoryName] = useState("");
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filterSubmenu, setFilterSubmenu] = useState<
    "vulnerability" | "sort" | "category" | null
  >(null);
  const filterRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!openMenu) return;
    const closeMenu = (event: PointerEvent) => {
      if (!(event.target as Element).closest(".action-menu")) setOpenMenu(null);
    };
    document.addEventListener("pointerdown", closeMenu);
    return () => document.removeEventListener("pointerdown", closeMenu);
  }, [openMenu]);
  const [editingService, setEditingService] = useState<Service | null>(null);
  const category = params.get("category") ?? "";
  const vulnerability = params.get("vulnerability") ?? "";
  const sort = params.get("service_sort") ?? "name";
  const page = Math.max(1, Number(params.get("service_page")) || 1);
  const categories = useQuery({
    queryKey: ["categories", "global"],
    queryFn: ({ signal }) => getCategories(platformId, signal),
  });
  const usedCategories = useQuery({
    queryKey: ["categories", platformId, "used"],
    queryFn: ({ signal }) => getCategories(platformId, signal, true),
  });
  const services = useQuery({
    queryKey: [
      "services",
      platformId,
      params.get("service_q") ?? "",
      category,
      vulnerability,
      sort,
      page,
    ],
    queryFn: ({ signal }) =>
      getServices(
        platformId,
        {
          q: params.get("service_q") ?? "",
          category_id:
            category && category !== "uncategorized" ? category : undefined,
          uncategorized: category === "uncategorized",
          vulnerable:
            vulnerability === "vulnerable"
              ? true
              : vulnerability === "safe"
                ? false
                : undefined,
          sort: sort as
            | "name"
            | "-name"
            | "created_at"
            | "-created_at"
            | "version"
            | "-version",
          page,
        },
        signal,
      ),
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => !item.last_checked_at)
        ? 1500
        : false,
  });
  const categoryCreation = useMutation({
    mutationFn: (name: string) => createCategory(platformId, name),
  });
  const categoryArchive = useMutation({ mutationFn: archiveCategory });
  const serviceArchive = useMutation({
    mutationFn: archiveService,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["services", platformId] }),
  });

  function updateParams(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([key, value]) =>
      value ? next.set(key, value) : next.delete(key),
    );
    setParams(next);
  }
  function choose(changes: Record<string, string>) {
    updateParams({ ...changes, service_page: "1" });
    setFiltersOpen(false);
  }
  function submitSearch(event: FormEvent) {
    event.preventDefault();
    updateParams({ service_q: search.trim(), service_page: "1" });
  }
  async function addCategory(event: FormEvent) {
    event.preventDefault();
    if (!categoryName.trim()) return;
    await categoryCreation.mutateAsync(categoryName.trim());
    setCategoryName("");
    await queryClient.invalidateQueries({
      queryKey: ["categories"],
    });
  }
  async function removeCategory(id: string) {
    if (
      !window.confirm(
        "Supprimer cette catégorie de l’affichage ? Les services seront conservés.",
      )
    )
      return;
    await categoryArchive.mutateAsync(id);
    await queryClient.invalidateQueries({
      queryKey: ["categories"],
    });
  }
  const totalPages = services.data
    ? Math.max(1, Math.ceil(services.data.total / 25))
    : 1;
  const activeFilterCount = [
    category,
    vulnerability,
    sort !== "name" ? sort : "",
  ].filter(Boolean).length;
  const closeCategories = () => {
    if (onToggleCategories) onToggleCategories();
    else setInternalCategoriesOpen(false);
  };

  return (
    <section className="services-panel" aria-labelledby="services-title">
      <div className="section-header">
        <h2 id="services-title">Services</h2>
        {!onToggleCategories && !archived && auth.hasPermission("service.create") && (
          <button
            type="button"
            onClick={() => setInternalCategoriesOpen((value) => !value)}
          >
            <FolderPlus aria-hidden="true" />
            Catégories
          </button>
        )}
      </div>
      {showCategories && (
        <ModalPortal>
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) closeCategories();
            }}
          >
            <section
              className="settings-modal category-management-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="categories-title"
            >
              <header className="settings-modal__header">
                <div>
                  <p className="eyebrow">Organisation des services</p>
                  <h2 id="categories-title">Catégories de la plateforme</h2>
                </div>
                <button
                  className="panel-icon-button"
                  type="button"
                  aria-label="Fermer les catégories"
                  data-tooltip="Fermer"
                  data-tooltip-placement="left"
                  onClick={closeCategories}
                >
                  <X aria-hidden="true" />
                </button>
              </header>

              <div className="category-management-modal__body">
                <form
                  className="category-create-form"
                  onSubmit={(event) => void addCategory(event)}
                >
                  <label htmlFor="new-category">Nouvelle catégorie</label>
                  <div className="search-control">
                    <input
                      id="new-category"
                      value={categoryName}
                      onChange={(event) => setCategoryName(event.target.value)}
                    />
                    <button type="submit" disabled={categoryCreation.isPending}>
                      Créer
                    </button>
                  </div>
                </form>

                {categoryCreation.error && (
                  <div className="form-error" role="alert">
                    {categoryCreation.error instanceof ApiError
                      ? categoryCreation.error.message
                      : "La création a échoué."}
                  </div>
                )}
                {categoryArchive.error && (
                  <div className="form-error" role="alert">
                    {categoryArchive.error instanceof ApiError
                      ? categoryArchive.error.message
                      : "La suppression a échoué."}
                  </div>
                )}

                <div className="category-management-modal__list-heading">
                  <h3>Toutes les catégories</h3>
                  <span>{categories.data?.length ?? 0}</span>
                </div>
                {categories.isPending && <p role="status">Chargement des catégories…</p>}
                {categories.isError && (
                  <div className="form-error" role="alert">
                    Impossible de charger les catégories.
                  </div>
                )}
                {categories.data?.length === 0 && (
                  <p className="empty-state">Aucune catégorie.</p>
                )}
                <ul className="category-list category-management-modal__list">
                  {categories.data?.map((item) => (
                    <li key={item.id}>
                      <span>{item.name}</span>
                      {auth.hasPermission("service.archive") && (
                        <button
                          className="panel-icon-button"
                          type="button"
                          onClick={() => void removeCategory(item.id)}
                          aria-label={`Supprimer ${item.name}`}
                          data-tooltip={`Supprimer ${item.name}`}
                          data-tooltip-placement="left"
                          disabled={categoryArchive.isPending}
                        >
                          <Trash2 aria-hidden="true" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          </div>
        </ModalPortal>
      )}
      <form
        className="service-filters service-filters--unified"
        onSubmit={submitSearch}
        role="search"
      >
        <div className="search-input combined-search-input">
          <input
            id="service-search"
            aria-label="Rechercher dans les services"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Rechercher dans les services"
          />
          <button type="submit" className="sr-only">
            Rechercher
          </button>
        <div className="custom-dropdown" ref={filterRef}>
          <button
            className="filter-trigger"
            type="button"
            aria-label="Filtrer"
            data-active-filter-count={activeFilterCount}
            aria-expanded={filtersOpen}
            onClick={() => {
              setFiltersOpen((open) => !open);
              setFilterSubmenu(null);
            }}
          >
            <Filter aria-hidden="true" />
            Filtrer par
            <ChevronDown aria-hidden="true" />
          </button>
          {filtersOpen && (
            <ViewportMenuPortal
              anchorRef={filterRef}
              className="custom-dropdown__menu filter-tree"
              ariaLabel="Filtres des services"
              onRequestClose={() => {
                setFiltersOpen(false);
                setFilterSubmenu(null);
              }}
            >
              <div
                className="filter-menu__item"
                onMouseEnter={() => setFilterSubmenu("vulnerability")}
              >
                <button
                  type="button"
                  onClick={() => setFilterSubmenu("vulnerability")}
                >
                  Vulnérabilité
                  <ChevronRight aria-hidden="true" />
                </button>
                {filterSubmenu === "vulnerability" && (
                  <div
                    className="filter-submenu"
                    role="menu"
                    aria-label="Vulnérabilité"
                  >
                    <button
                      type="button"
                      onClick={() => choose({ vulnerability: "" })}
                    >
                      Toutes
                    </button>
                    <button
                      type="button"
                      onClick={() => choose({ vulnerability: "vulnerable" })}
                    >
                      Vulnérables
                    </button>
                    <button
                      type="button"
                      onClick={() => choose({ vulnerability: "safe" })}
                    >
                      Sans vulnérabilité connue
                    </button>
                  </div>
                )}
              </div>
              <div
                className="filter-menu__item"
                onMouseEnter={() => setFilterSubmenu("sort")}
              >
                <button type="button" onClick={() => setFilterSubmenu("sort")}>
                  Ordre
                  <ChevronRight aria-hidden="true" />
                </button>
                {filterSubmenu === "sort" && (
                  <div
                    className="filter-submenu"
                    role="menu"
                    aria-label="Ordre"
                  >
                    <button
                      type="button"
                      onClick={() => choose({ service_sort: "-created_at" })}
                    >
                      Derniers ajoutés
                    </button>
                    <button
                      type="button"
                      onClick={() => choose({ service_sort: "created_at" })}
                    >
                      Premiers ajoutés
                    </button>
                    <button
                      type="button"
                      onClick={() => choose({ service_sort: "name" })}
                    >
                      Nom A–Z
                    </button>
                  </div>
                )}
              </div>
              <div
                className="filter-menu__item"
                onMouseEnter={() => setFilterSubmenu("category")}
              >
                <button
                  type="button"
                  onClick={() => setFilterSubmenu("category")}
                >
                  Catégorie
                  <ChevronRight aria-hidden="true" />
                </button>
                {filterSubmenu === "category" && (
                  <div
                    className="filter-submenu"
                    role="menu"
                    aria-label="Catégorie"
                  >
                    <button
                      type="button"
                      onClick={() => choose({ category: "" })}
                    >
                      Toutes
                    </button>
                    <button
                      type="button"
                      onClick={() => choose({ category: "uncategorized" })}
                    >
                      Non catégorisé
                    </button>
                    {usedCategories.data?.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => choose({ category: item.id })}
                      >
                        {item.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </ViewportMenuPortal>
          )}
        </div>
        </div>
      </form>
      {services.isPending && <p role="status">Chargement des services…</p>}
      {services.isError && (
        <div className="form-error" role="alert">
          {services.error instanceof ApiError
            ? services.error.message
            : "Impossible de charger les services."}
        </div>
      )}
      {services.data?.items.length === 0 && (
        <p className="empty-state">Aucun service ne correspond aux filtres.</p>
      )}
      {services.data && services.data.items.length > 0 && (
        <div className="table-wrapper">
          <table className="service-table">
            <thead>
              <tr>
                <th>Nom du service</th>
                <th>Version</th>
                <th>Vulnérabilité</th>
              </tr>
            </thead>
            <tbody>
              {services.data.items.map((service) => (
                <tr key={service.id}>
                  <td>
                    <Link to={`/services/${service.id}`}>{service.name}</Link>
                  </td>
                  <td>{service.version ?? "Non renseignée"}</td>
                  <td>
                    <div className="vulnerability-cell">
                      {!service.last_checked_at ? (
                        <span>Vérification…</span>
                      ) : (service.active_vulnerability_count ?? 0) > 0 ? (
                        <span className="vulnerable-label">
                          Vulnérable{" "}
                          <Link to={`/services/${service.id}`}>Détail</Link>
                        </span>
                      ) : ["version_not_found", "ambiguous_ecosystem"].includes(
                          service.security_identity?.status ?? "",
                        ) ? (
                        <span>Identité à vérifier</span>
                      ) : (
                        <span>Aucune vulnérabilité connue</span>
                      )}
                      <div className="action-menu">
                        <button
                          className="service-row-action"
                          type="button"
                          aria-label={`Actions pour ${service.name}`}
                          data-tooltip={`Actions pour ${service.name}`}
                          data-tooltip-placement="left"
                          onClick={() =>
                            setOpenMenu((current) =>
                              current === service.id ? null : service.id,
                            )
                          }
                        >
                          <MoreHorizontal aria-hidden="true" />
                        </button>
                        {openMenu === service.id && (
                          <div className="action-menu__content">
                            {auth.hasPermission("service.update") && (
                              <button
                                type="button"
                                onClick={() => {
                                  setEditingService(service);
                                  setOpenMenu(null);
                                }}
                              >
                                Modifier
                              </button>
                            )}
                            {auth.hasPermission("service.archive") && (
                              <button
                                type="button"
                                onClick={() => {
                                  serviceArchive.mutate(service.id);
                                  setOpenMenu(null);
                                }}
                              >
                                Supprimer
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {services.data && totalPages > 1 && (
        <nav className="pagination" aria-label="Pagination des services">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => updateParams({ service_page: String(page - 1) })}
          >
            Précédent
          </button>
          <span>
            Page {page} sur {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => updateParams({ service_page: String(page + 1) })}
          >
            Suivant
          </button>
        </nav>
      )}
      {editingService && (
        <ServiceEditModal
          service={editingService}
          categories={categories.data ?? []}
          onClose={() => setEditingService(null)}
          onSaved={async () => {
            await Promise.all([
              queryClient.invalidateQueries({
                queryKey: ["services", platformId],
              }),
              queryClient.invalidateQueries({
                queryKey: ["service", editingService.id],
              }),
              queryClient.invalidateQueries({ queryKey: ["platforms"] }),
              queryClient.invalidateQueries({
                queryKey: ["categories", platformId, "used"],
              }),
            ]);
          }}
        />
      )}
    </section>
  );
}
