import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import type { PlatformInput, PlatformTargetType } from "../../api/platforms";
import { CustomSelect } from "../../components/CustomSelect";

const schema = z
  .object({
    name: z.string().trim().min(1, "Le nom est obligatoire.").max(200),
    target_type: z.enum(["none", "url", "ip"]),
    target_value: z.string().max(2048),
  })
  .superRefine((values, context) => {
    if (values.target_type !== "none" && !values.target_value.trim()) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["target_value"],
        message: values.target_type === "url" ? "L’URL est obligatoire." : "L’adresse IP est obligatoire.",
      });
    }
  });

type FormValues = z.infer<typeof schema>;

type Props = {
  initial?: PlatformInput;
  submitLabel: string;
  pending: boolean;
  error?: string | null;
  onSubmit: (input: PlatformInput) => Promise<void>;
  onCancel: () => void;
};

export function PlatformForm({ initial, submitLabel, pending, error, onSubmit, onCancel }: Props) {
  const { control, register, handleSubmit, watch, formState } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: initial?.name ?? "",
      target_type: initial?.target_type ?? "none",
      target_value: initial?.target_value ?? "",
    },
  });
  const targetType = watch("target_type") as PlatformTargetType;

  const submit = handleSubmit(async (values) => {
    await onSubmit({
      name: values.name.trim(),
      target_type: values.target_type,
      target_value: values.target_type === "none" ? null : values.target_value.trim(),
      description: initial?.description ?? null,
    });
  });

  return (
    <form className="platform-form" onSubmit={submit} noValidate>
      <div className="form-field">
        <label htmlFor="platform-name">Nom de la plateforme</label>
        <input id="platform-name" {...register("name")} />
        {formState.errors.name && <p className="field-error">{formState.errors.name.message}</p>}
      </div>
      <div className="form-field">
        <label htmlFor="target-type">Type de cible</label>
        <Controller
          control={control}
          name="target_type"
          render={({ field }) => (
            <CustomSelect
              id="target-type"
              value={field.value}
              onChange={field.onChange}
              options={[
                { value: "none", label: "Aucune cible" },
                { value: "url", label: "URL" },
                { value: "ip", label: "Adresse IP" },
              ]}
            />
          )}
        />
      </div>
      {targetType !== "none" && (
        <div className="form-field">
          <label htmlFor="target-value">{targetType === "url" ? "URL" : "Adresse IP"}</label>
          <input
            id="target-value"
            placeholder={targetType === "url" ? "https://exemple.ma" : "192.0.2.10"}
            {...register("target_value")}
          />
          {formState.errors.target_value && (
            <p className="field-error">{formState.errors.target_value.message}</p>
          )}
        </div>
      )}
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-actions">
        <button type="button" onClick={onCancel}>Annuler</button>
        <button className="primary-button" type="submit" disabled={pending}>
          {pending ? "Enregistrement…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
