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

export function AICategorizationReview({
  platformId,
  items,
  disabled = false,
  onConfirmed,
}: {
  platformId: string;
  items: AICategorizationInput[];
  disabled?: boolean;
  onConfirmed: (items: { key: string; category: Category }[]) => void | Promise<void>;
}) {
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const names = useMemo(
    () => new Map(items.map((item) => [item.key, item.name])),
    [items],
  );
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
    onSuccess: async (data) => {
      await onConfirmed(data.items);
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
                <p>Décochez ou modifiez les suggestions avant leur création.</p>
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
              {rows.map((row, index) => (
                <div className="ai-review-row" key={row.key}>
                  <label className="ai-review-check">
                    <input
                      type="checkbox"
                      checked={row.selected}
                      onChange={(event) =>
                        setRows((current) =>
                          current?.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, selected: event.target.checked }
                              : item,
                          ) ?? null,
                        )
                      }
                    />
                    <span>{names.get(row.key) ?? `Service ${index + 1}`}</span>
                  </label>
                  <input
                    aria-label={`Catégorie pour ${names.get(row.key) ?? `service ${index + 1}`}`}
                    value={row.category_name}
                    disabled={!row.selected}
                    onChange={(event) =>
                      setRows((current) =>
                        current?.map((item, itemIndex) =>
                          itemIndex === index
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
                {confirmation.isPending ? "Confirmation…" : "Confirmer les catégories"}
              </button>
            </div>
            </section>
          </div>
        </ModalPortal>
      )}
    </>
  );
}
