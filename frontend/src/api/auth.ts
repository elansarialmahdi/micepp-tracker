import { apiRequest, setAccessToken, setRefreshAccessToken } from "./client";
import type { LoginValues, TokenResponse } from "../auth/types";

let refreshPromise: Promise<TokenResponse> | null = null;

function acceptTokens(tokens: TokenResponse): TokenResponse {
  setAccessToken(tokens.access_token, tokens.expires_in);
  return tokens;
}

export async function loginRequest(values: LoginValues): Promise<TokenResponse> {
  const result = await apiRequest<TokenResponse>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(values),
  });
  return acceptTokens(result);
}

export function refreshRequest(): Promise<TokenResponse> {
  if (!refreshPromise) {
    refreshPromise = apiRequest<TokenResponse>(
      "/v1/auth/refresh",
      { method: "POST" },
      { csrf: true },
    )
      .then(acceptTokens)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

setRefreshAccessToken(refreshRequest);

export async function logoutRequest(): Promise<void> {
  try {
    await apiRequest("/v1/auth/logout", { method: "POST" }, { csrf: true });
  } finally {
    setAccessToken(null);
  }
}

export async function changePasswordRequest(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await apiRequest(
    "/v1/auth/change-password",
    {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    },
    { authenticated: true },
  );
  setAccessToken(null);
}
