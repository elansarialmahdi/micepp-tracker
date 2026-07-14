import { apiRequest } from "./client";

export type PlatformTargetType = "url" | "ip" | "none";

export type Platform = {
  id: string;
  name: string;
  target_type: PlatformTargetType;
  target_value: string | null;
  normalized_target: string | null;
  description: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  last_inventory_scan_at: string | null;
  last_vulnerability_check_at: string | null;
  archived_at: string | null;
  service_count?: number;
  threat_count?: number;
};

export type PlatformInput = {
  name: string;
  target_type: PlatformTargetType;
  target_value: string | null;
  description: string | null;
};

export type PlatformList = {
  items: Platform[];
  total: number;
  page: number;
  page_size: number;
};

export type PlatformFilters = {
  q?: string;
  target_type?: PlatformTargetType | "";
  sort?: "created_at" | "-created_at" | "name" | "-name";
  page?: number;
  page_size?: number;
};

export function getPlatforms(filters: PlatformFilters, signal?: AbortSignal): Promise<PlatformList> {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.target_type) params.set("target_type", filters.target_type);
  if (filters.sort) params.set("sort", filters.sort);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.page_size ?? 12));
  return apiRequest<PlatformList>(`/v1/platforms?${params}`, { signal }, { authenticated: true });
}

export function getPlatform(id: string, signal?: AbortSignal): Promise<Platform> {
  return apiRequest<Platform>(`/v1/platforms/${id}`, { signal }, { authenticated: true });
}

export function createPlatform(input: PlatformInput): Promise<Platform> {
  return apiRequest<Platform>(
    "/v1/platforms",
    { method: "POST", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export function updatePlatform(id: string, input: PlatformInput): Promise<Platform> {
  return apiRequest<Platform>(
    `/v1/platforms/${id}`,
    { method: "PATCH", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export function archivePlatform(id: string): Promise<Platform> {
  return apiRequest<Platform>(
    `/v1/platforms/${id}`,
    { method: "DELETE" },
    { authenticated: true },
  );
}
