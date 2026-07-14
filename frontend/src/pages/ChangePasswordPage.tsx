import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";

const schema = z.object({
  currentPassword: z.string().min(1, "Le mot de passe actuel est obligatoire."),
  newPassword: z.string().min(12, "Utilisez au moins 12 caractères."),
  confirmation: z.string(),
}).refine((values) => values.newPassword === values.confirmation, {
  path: ["confirmation"],
  message: "Les mots de passe ne correspondent pas.",
});

type FormValues = z.infer<typeof schema>;

export function ChangePasswordPage() {
  const auth = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const submit = handleSubmit(async (values) => {
    setServerError(null);
    try {
      await auth.changePassword(values.currentPassword, values.newPassword);
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Le serveur est indisponible.");
    }
  });

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="password-title">
        <p className="eyebrow">Sécurité du compte</p>
        <h1 id="password-title">Modifier le mot de passe initial</h1>
        <p className="intro">Cette étape est obligatoire avant d’accéder à l’application.</p>
        <form onSubmit={submit} noValidate>
          <div className="form-field">
            <label htmlFor="current-password">Mot de passe actuel</label>
            <input id="current-password" type="password" autoComplete="current-password" {...register("currentPassword")} />
            {formState.errors.currentPassword && <p className="field-error">{formState.errors.currentPassword.message}</p>}
          </div>
          <div className="form-field">
            <label htmlFor="new-password">Nouveau mot de passe</label>
            <input id="new-password" type="password" autoComplete="new-password" {...register("newPassword")} />
            {formState.errors.newPassword && <p className="field-error">{formState.errors.newPassword.message}</p>}
          </div>
          <div className="form-field">
            <label htmlFor="confirmation">Confirmer le nouveau mot de passe</label>
            <input id="confirmation" type="password" autoComplete="new-password" {...register("confirmation")} />
            {formState.errors.confirmation && <p className="field-error">{formState.errors.confirmation.message}</p>}
          </div>
          <p className="password-hint">12 caractères minimum avec majuscule, minuscule, chiffre et caractère spécial.</p>
          {serverError && <div className="form-error" role="alert">{serverError}</div>}
          <button className="primary-button" type="submit" disabled={formState.isSubmitting}>Modifier et se reconnecter</button>
        </form>
      </section>
    </main>
  );
}

