export type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string | null;
  };
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string | null,
  ) {
    super(message);
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
let accessToken: string | null = null;
let accessTokenExpiresAt = 0;
let refreshAccessToken: (() => Promise<unknown>) | null = null;

export function setAccessToken(token: string | null, expiresInSeconds = 0): void {
  accessToken = token;
  accessTokenExpiresAt = token ? Date.now() + expiresInSeconds * 1000 : 0;
}

export function setRefreshAccessToken(handler: () => Promise<unknown>): void {
  refreshAccessToken = handler;
}

export function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split("; ").find((cookie) => cookie.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  options: { authenticated?: boolean; csrf?: boolean } = {},
): Promise<T> {
  return request<T>(path, init, options, true);
}

async function request<T>(
  path: string,
  init: RequestInit,
  options: { authenticated?: boolean; csrf?: boolean },
  allowRefresh: boolean,
): Promise<T> {
  if (
    options.authenticated
    && allowRefresh
    && accessToken
    && refreshAccessToken
    && accessTokenExpiresAt > 0
    && accessTokenExpiresAt - Date.now() < 30_000
  ) {
    try {
      await refreshAccessToken();
    } catch {
      setAccessToken(null);
    }
  }
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (options.authenticated && accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  if (options.csrf) {
    const csrf = readCookie("micepp_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (response.status === 401 && options.authenticated && allowRefresh && refreshAccessToken) {
    try {
      await refreshAccessToken();
      return request<T>(path, init, options, false);
    } catch {
      setAccessToken(null);
      // Preserve the original API response: it carries the most relevant error.
    }
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ApiErrorPayload;
    throw new ApiError(
      response.status,
      payload.error?.code ?? "UNEXPECTED_ERROR",
      payload.error?.message ?? "Une erreur inattendue est survenue.",
      payload.error?.request_id,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
