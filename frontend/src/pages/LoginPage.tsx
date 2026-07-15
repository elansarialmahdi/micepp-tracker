import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router";
import { z } from "zod";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { ToggleSwitch } from "../components/ToggleSwitch";

const schema = z.object({
  username: z.string().trim().min(1, "L’identifiant est obligatoire."),
  password: z.string().min(1, "Le mot de passe est obligatoire."),
  remember_me: z.boolean(),
});

type LoginForm = z.infer<typeof schema>;

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [serverError, setServerError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<LoginForm>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "", remember_me: false },
  });

  if (auth.status === "loading") {
    return <p className="route-status" role="status">Chargement de la session…</p>;
  }
  if (auth.status === "authenticated") {
    return <Navigate to={auth.user?.must_change_password ? "/change-password" : "/"} replace />;
  }

  const submit = handleSubmit(async (values) => {
    setServerError(null);
    try {
      const user = await auth.login(values);
      const requestedPath = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(user.must_change_password ? "/change-password" : requestedPath, { replace: true });
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Le serveur est indisponible.");
    }
  });

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <img className="auth-logo" src="/assets/micepp-logo.png" alt="" aria-hidden="true" />
        <h1 id="login-title">MICEPP - TRACKER</h1>
        <p className="auth-subtitle">Accès sécurisé</p>
        <form onSubmit={submit} noValidate>
          <div className="form-field">
            <label className="sr-only" htmlFor="username">Identifiant</label>
            <input id="username" placeholder="Identifiant" autoComplete="username" {...register("username")} />
            {formState.errors.username && <p className="field-error">{formState.errors.username.message}</p>}
          </div>
          <div className="form-field">
            <label className="sr-only" htmlFor="password">Mot de passe</label>
            <input id="password" placeholder="Mot de passe" type="password" autoComplete="current-password" {...register("password")} />
            {formState.errors.password && <p className="field-error">{formState.errors.password.message}</p>}
          </div>
          <div className="checkbox-field">
            <ToggleSwitch
              id="remember-me"
              aria-label="Rester connecté"
              {...register("remember_me")}
            />
            <label htmlFor="remember-me">Rester connecté</label>
          </div>
          {serverError && <div className="form-error" role="alert">{serverError}</div>}
          <button className="primary-button" type="submit" disabled={formState.isSubmitting}>
            {formState.isSubmitting ? "Connexion…" : "Se connecter"}
          </button>
        </form>
      </section>
    </main>
  );
}
