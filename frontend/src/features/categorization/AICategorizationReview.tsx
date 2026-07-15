import { useMutation } from "@tanstack/react-query";
import { Sparkles, X } from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import {
  confirmServiceCategorization,
  previewServiceCategorization,
  type AICategorizationInput,
  type AICategorizationPreviewSuggestion,
  type Category,
} from "../../api/inventory";
import { ModalPortal } from "../../components/ModalPortal";

type ReviewRow = AICategorizationPreviewSuggestion & { selected: boolean };

type ReviewCategory = {
  key: string;
  categoryName: string;
  selected: boolean;
  indexes: number[];
};

function normalizedCategoryName(value: string): string {
  return value.trim().toLocaleLowerCase("fr-FR");
}

export function AICategorizationReview({
  platformId,
  items,
  disabled = false,
  onConfirmed,
}: {
  platformId: string;
  items: AICategorizationInput[];
  disabled?: boolean;
  onConfirmed: (items: { key: string; category: Category | null }[]) => void | Promise<void>;
}) {
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const categories = useMemo(() => {
    if (!rows) return [];
    const grouped = new Map<string, ReviewCategory>();
    rows.forEach((row, index) => {
      const key = normalizedCategoryName(row.category_name);
      const current = grouped.get(key);
      if (current) {
        current.indexes.push(index);
        current.selected = current.selected || row.selected;
        return;
      }
      grouped.set(key, {
        key,
        categoryName: row.category_name,
        selected: row.selected,
        indexes: [index],
      });
    });
    return [...grouped.values()];
  }, [rows]);
  const preview = useMutation({
    mutationFn: () => previewServiceCategorization(platformId, items),
    onSuccess: (data) =>
      setRows(data.items.map((item) => ({ ...item, selected: true }))),
  });
  const confirmation = useMutation({
    mutationFn: (reviewRows: ReviewRow[]) =>
      confirmServiceCategorization(
        platformId,
        reviewRows.map((row) => ({
          key: row.key,
          category_name: row.category_name.trim(),
          selected: row.selected,
        })),
      ),
    onSuccess: async (data, reviewRows) => {
      const confirmedByKey = new Map(data.items.map((item) => [item.key, item.category]));
      await onConfirmed(
        reviewRows.map((row) => ({
          key: row.key,
          category: row.selected ? confirmedByKey.get(row.key) ?? null : null,
        })),
      );
      setRows(null);
    },
  });
  const error = preview.error ?? confirmation.error;

  return (
    <>
      <button
        className="ai-categorization-button"
        type="button"
        disabled={disabled || preview.isPending || items.length === 0}
        onClick={() => preview.mutate()}
      >
        <Sparkles aria-hidden="true" />
        {preview.isPending ? "Analyse en cours…" : "Catégorisation par IA"}
      </button>
      {error && (
        <div className="form-error" role="alert">
          {error instanceof ApiError
            ? error.message
            : "La catégorisation IA a échoué."}
        </div>
      )}
      {rows && (
        <ModalPortal>
          <div
            className="modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setRows(null);
            }}
          >
            <section
              className="settings-modal ai-review-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="ai-review-title"
            >
            <div className="section-header">
              <div>
                <h2 id="ai-review-title">Confirmer les catégories</h2>
                <p>Décochez ou renommez les catégories proposées avant la confirmation finale.</p>
              </div>
              <button
                className="modal-close"
                type="button"
                aria-label="Fermer"
                data-tooltip="Fermer"
                data-tooltip-placement="bottom"
                onClick={() => setRows(null)}
              >
                <X aria-hidden="true" />
              </button>
            </div>
            <div className="ai-review-list">
              {categories.map((category) => (
                <div className="ai-review-row" key={category.key}>
                  <label className="ai-review-check">
                    <input
                      type="checkbox"
                      checked={category.selected}
                      onChange={(event) =>
                        setRows((current) =>
                          current?.map((item, itemIndex) =>
                            category.indexes.includes(itemIndex)
                              ? { ...item, selected: event.target.checked }
                              : item,
                          ) ?? null,
                        )
                      }
                      aria-label={`Conserver la catégorie ${category.categoryName}`}
                    />
                  </label>
                  <input
                    aria-label={`Nom de la catégorie ${category.categoryName}`}
                    value={category.categoryName}
                    disabled={!category.selected}
                    onChange={(event) =>
                      setRows((current) =>
                        current?.map((item, itemIndex) =>
                          category.indexes.includes(itemIndex)
                            ? { ...item, category_name: event.target.value }
                            : item,
                        ) ?? null,
                      )
                    }
                  />
                </div>
              ))}
            </div>
            <div className="form-actions">
              <button type="button" onClick={() => setRows(null)}>Annuler</button>
              <button
                className="primary-button"
                type="button"
                disabled={
                  confirmation.isPending ||
                  !rows.some((row) => row.selected && row.category_name.trim())
                }
                onClick={() => confirmation.mutate(rows)}
              >
                {confirmation.isPending ? "Confirmation…" : "Confirmer la sélection"}
              </button>
            </div>
            </section>
          </div>
        </ModalPortal>
      )}
    </>
  );
}
