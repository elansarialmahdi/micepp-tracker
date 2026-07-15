import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, MinusCircle, Plus } from "lucide-react";
import { useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router";
import { z } from "zod";

import { ApiError } from "../api/client";
import {
  createCategory,
  createServices,
  getCategories,
} from "../api/inventory";
import { useAuth } from "../auth/AuthProvider";
import { CustomSelect } from "../components/CustomSelect";
import { AICategorizationReview } from "../features/categorization/AICategorizationReview";

const rowSchema = z.object({
  name: z.string().trim().min(1, "Le nom est obligatoire."),
  version: z.string(),
  category_id: z.string(),
});

const schema = z
  .object({ items: z.array(rowSchema).min(1).max(100) })
  .superRefine((values, context) => {
    const keys = new Set<string>();
    values.items.forEach((item, index) => {
      const key = `${item.name.trim().toLocaleLowerCase()}::${item.version.trim().toLocaleLowerCase()}`;
      if (keys.has(key)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["items", index, "name"],
          message: "Cette ligne est en double.",
        });
      }
      keys.add(key);
    });
  });

type FormValues = z.infer<typeof schema>;

export function AddServicesPage({
  embedded = false,
  onClose,
  onSwitchToImport,
}: {
  embedded?: boolean;
  onClose?: () => void;
  onSwitchToImport?: () => void;
} = {}) {
  const { platformId = "" } = useParams();
  const auth = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [categoryName, setCategoryName] = useState("");
  const categories = useQuery({
    queryKey: ["categories", "global"],
    queryFn: ({ signal }) => getCategories(platformId, signal),
  });
  const creation = useMutation({
    mutationFn: (items: FormValues["items"]) =>
      createServices(
        platformId,
        items.map((item) => ({
          name: item.name.trim(),
          version: item.version.trim() || null,
          category_id: item.category_id || null,
        })),
      ),
  });
  const categoryCreation = useMutation({
    mutationFn: (name: string) => createCategory(platformId, name),
  });
  const { control, register, handleSubmit, formState, watch, setValue } =
    useForm<FormValues>({
      resolver: zodResolver(schema),
      defaultValues: { items: [{ name: "", version: "", category_id: "" }] },
    });
  const rows = useFieldArray({ control, name: "items" });
  const watchedItems = watch("items");

  if (!auth.hasPermission("service.create")) {
    return (
      <div className="form-error" role="alert">
        Vous n’avez pas l’autorisation d’ajouter des services.
      </div>
    );
  }

  async function addCategory() {
    if (!categoryName.trim()) return;
    await categoryCreation.mutateAsync(categoryName.trim());
    setCategoryName("");
    await queryClient.invalidateQueries({
      queryKey: ["categories"],
    });
  }

  const submit = handleSubmit(async (values) => {
    await creation.mutateAsync(values.items);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["services", platformId] }),
      queryClient.invalidateQueries({
        queryKey: ["categories", platformId, "used"],
      }),
    ]);
    if (onClose) onClose();
    else navigate(`/platforms/${platformId}`);
  });

  return (
    <section
      aria-labelledby={embedded ? undefined : "add-services-title"}
      aria-label={embedded ? "Formulaire d’ajout manuel" : undefined}
    >
      {!embedded && (
        <Link className="back-link" to={`/platforms/${platformId}`}>
          <ArrowLeft aria-hidden="true" />
          Retour à la plateforme
        </Link>
      )}
      {!embedded && (
        <>
          <p className="eyebrow">Ajout manuel</p>
          <h1 id="add-services-title">Ajouter des services</h1>
        </>
      )}
      {auth.hasPermission("service.import") && onSwitchToImport && (
        <p className="method-switch">
          Vous avez un classeur existant ?{" "}
          <button
            className="link-button"
            type="button"
            onClick={onSwitchToImport}
          >
            Importer un fichier Excel
          </button>
          .
        </p>
      )}
      <div className="inline-category-form">
        <label htmlFor="wizard-category">Créer une catégorie (optionnel)</label>
        <div className="search-control">
          <input
            id="wizard-category"
            value={categoryName}
            onChange={(event) => setCategoryName(event.target.value)}
          />
          <button
            type="button"
            onClick={() => void addCategory()}
            disabled={categoryCreation.isPending}
          >
            Créer
          </button>
        </div>
        {categoryCreation.error && (
          <div className="form-error" role="alert">
            {categoryCreation.error instanceof ApiError
              ? categoryCreation.error.message
              : "La création a échoué."}
          </div>
        )}
      </div>

      <form className="bulk-service-form" onSubmit={submit} noValidate>
        {rows.fields.map((row, index) => (
          <fieldset key={row.id} className="service-form-row">
            <legend>Service {index + 1}</legend>
            <div className="form-field">
              <label htmlFor={`service-name-${index}`}>Nom du service</label>
              <input
                id={`service-name-${index}`}
                {...register(`items.${index}.name`)}
              />
              {formState.errors.items?.[index]?.name && (
                <p className="field-error">
                  {formState.errors.items[index]?.name?.message}
                </p>
              )}
            </div>
            <div className="form-field">
              <label htmlFor={`service-version-${index}`}>
                Version (optionnelle)
              </label>
              <input
                id={`service-version-${index}`}
                {...register(`items.${index}.version`)}
              />
            </div>
            <div className="form-field">
              <label htmlFor={`service-category-${index}`}>Catégorie</label>
              <Controller
                control={control}
                name={`items.${index}.category_id`}
                render={({ field }) => (
                  <CustomSelect
                    id={`service-category-${index}`}
                    value={field.value}
                    onChange={field.onChange}
                    options={[
                      { value: "", label: "Non catégorisé" },
                      ...(categories.data ?? []).map((category) => ({
                        value: category.id,
                        label: category.name,
                      })),
                    ]}
                  />
                )}
              />
            </div>
            <button
              type="button"
              onClick={() => rows.remove(index)}
              disabled={rows.fields.length === 1}
            >
              <MinusCircle aria-hidden="true" />
              Retirer la ligne
            </button>
          </fieldset>
        ))}
        <button
          type="button"
          onClick={() =>
            rows.append({ name: "", version: "", category_id: "" })
          }
        >
          <Plus aria-hidden="true" />
          Ajouter une ligne
        </button>
        <AICategorizationReview
          platformId={platformId}
          items={watchedItems
            .filter((item) => item.name.trim())
            .map((item, index) => ({
              key: String(index),
              name: item.name.trim(),
              version: item.version.trim() || null,
            }))}
          disabled={watchedItems.some((item) => !item.name.trim())}
          onConfirmed={async (suggestions) => {
            suggestions.forEach((suggestion) => {
              setValue(
                `items.${Number(suggestion.key)}.category_id`,
                suggestion.category?.id ?? "",
                { shouldDirty: true },
              );
            });
            await queryClient.invalidateQueries({ queryKey: ["categories"] });
          }}
        />
        {creation.error && (
          <div className="form-error" role="alert">
            {creation.error instanceof ApiError
              ? creation.error.message
              : "L’ajout a échoué."}
          </div>
        )}
        <div className="form-actions">
          <button
            type="button"
            onClick={() =>
              onClose ? onClose() : navigate(`/platforms/${platformId}`)
            }
          >
            Annuler
          </button>
          <button
            className="primary-button"
            type="submit"
            disabled={creation.isPending}
          >
            {creation.isPending ? "Ajout…" : "Confirmer l’ajout"}
          </button>
        </div>
      </form>
    </section>
  );
}
