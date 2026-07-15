import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Plus, Search } from "lucide-react";
import { type FormEvent, useMemo, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { createCategory, getCategories, type Category } from "../api/inventory";
import { ViewportMenuPortal } from "./ViewportMenuPortal";

type CategoryPickerProps = {
  platformId: string;
  value: string | null;
  valueType?: "id" | "name";
  ariaLabel: string;
  disabled?: boolean;
  allowCreate?: boolean;
  onChange: (value: string | null) => void;
};

function normalized(value: string): string {
  return value.trim().toLocaleLowerCase("fr-FR");
}

export function CategoryPicker({
  platformId,
  value,
  valueType = "name",
  ariaLabel,
  disabled = false,
  allowCreate = true,
  onChange,
}: CategoryPickerProps) {
  const queryClient = useQueryClient();
  const anchorRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const categories = useQuery({
    queryKey: ["categories", "global"],
    queryFn: ({ signal }) => getCategories(platformId, signal),
  });
  const selected = categories.data?.find((category) =>
    valueType === "id"
      ? category.id === value
      : normalized(category.name) === normalized(value ?? ""),
  );
  const filteredCategories = useMemo(() => {
    const needle = normalized(search);
    if (!needle) return categories.data ?? [];
    return (categories.data ?? []).filter((category) =>
      normalized(category.name).includes(needle),
    );
  }, [categories.data, search]);

  function categoryValue(category: Category): string {
    return valueType === "id" ? category.id : category.name;
  }

  function close() {
    setOpen(false);
    setSearch("");
    setCreating(false);
    setName("");
    setError(null);
  }

  async function submitCreation(event: FormEvent) {
    event.preventDefault();
    const nextName = name.trim();
    if (!nextName) return;
    setPending(true);
    setError(null);
    try {
      const category = await createCategory(platformId, nextName);
      await queryClient.invalidateQueries({ queryKey: ["categories"] });
      onChange(categoryValue(category));
      close();
    } catch (creationError) {
      setError(
        creationError instanceof ApiError
          ? creationError.message
          : "La catégorie n’a pas pu être créée.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="category-picker" ref={anchorRef}>
      <button
        className="category-picker__trigger"
        type="button"
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="listbox"
        disabled={disabled || categories.isPending}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{selected?.name ?? (valueType === "name" ? value : null) ?? "Non catégorisé"}</span>
        <ChevronDown aria-hidden="true" />
      </button>
      {open && (
        <ViewportMenuPortal
          anchorRef={anchorRef}
          className="category-picker-menu"
          ariaLabel={ariaLabel}
          onRequestClose={close}
        >
          <label className="category-picker-menu__search">
            <Search aria-hidden="true" />
            <input
              autoFocus
              aria-label="Rechercher une catégorie"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Rechercher"
            />
          </label>
          <div className="category-picker-menu__options" role="listbox">
            <button
              type="button"
              role="option"
              aria-selected={!value}
              onClick={() => {
                onChange(null);
                close();
              }}
            >
              <span>Non catégorisé</span>
              {!value && <Check aria-hidden="true" />}
            </button>
            {filteredCategories.map((category) => {
              const active = category.id === selected?.id;
              return (
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  key={category.id}
                  onClick={() => {
                    onChange(categoryValue(category));
                    close();
                  }}
                >
                  <span>{category.name}</span>
                  {active && <Check aria-hidden="true" />}
                </button>
              );
            })}
            {filteredCategories.length === 0 && (
              <p className="category-picker-menu__empty">Aucune catégorie</p>
            )}
          </div>
          {allowCreate && (
            <div className="category-picker-menu__create">
              {creating ? (
                <form onSubmit={(event) => void submitCreation(event)}>
                  <input
                    autoFocus
                    aria-label="Nom de la nouvelle catégorie"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Nouvelle catégorie"
                  />
                  <button
                    type="submit"
                    aria-label="Créer et sélectionner la catégorie"
                    disabled={pending || !name.trim()}
                  >
                    <Check aria-hidden="true" />
                  </button>
                </form>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setName(search);
                    setCreating(true);
                  }}
                >
                  <Plus aria-hidden="true" />
                  Créer une catégorie
                </button>
              )}
              {error && <p className="field-error" role="alert">{error}</p>}
            </div>
          )}
        </ViewportMenuPortal>
      )}
    </div>
  );
}
