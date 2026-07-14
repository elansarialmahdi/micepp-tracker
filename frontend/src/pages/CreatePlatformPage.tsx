import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { createPlatform, type PlatformInput } from "../api/platforms";
import { useAuth } from "../auth/AuthProvider";
import { PlatformForm } from "../features/platforms/PlatformForm";

export function CreatePlatformPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const creation = useMutation({ mutationFn: createPlatform });

  if (!auth.hasPermission("platform.create")) {
    return <div className="form-error" role="alert">Vous n’avez pas l’autorisation de créer une plateforme.</div>;
  }

  async function submit(input: PlatformInput) {
    const platform = await creation.mutateAsync(input);
    await queryClient.invalidateQueries({ queryKey: ["platforms"] });
    navigate(`/platforms/${platform.id}`);
  }

  return (
    <section className="form-page" aria-labelledby="create-platform-title">
      <p className="eyebrow">Plateformes</p>
      <h1 id="create-platform-title">Créer une plateforme</h1>
      <PlatformForm
        submitLabel="Créer la plateforme"
        pending={creation.isPending}
        error={creation.error instanceof ApiError ? creation.error.message : creation.error ? "Le serveur est indisponible." : null}
        onSubmit={submit}
        onCancel={() => navigate("/platforms")}
      />
    </section>
  );
}

