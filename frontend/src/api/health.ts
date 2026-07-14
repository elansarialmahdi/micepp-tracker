export type LivenessResponse = {
  status: "ok";
  service: string;
  version: string;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export async function getLiveness(signal?: AbortSignal): Promise<LivenessResponse> {
  const response = await fetch(`${API_BASE_URL}/health/live`, {
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new Error("Le service API est indisponible.");
  }

  return response.json() as Promise<LivenessResponse>;
}

