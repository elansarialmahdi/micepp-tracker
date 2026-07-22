import { apiRequest } from "./client";

export type Category = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type Service = {
  id: string;
  platform_id: string;
  category_id: string | null;
  category_name: string | null;
  name: string;
  vendor: string | null;
  product: string | null;
  version: string | null;
  cpe_uri: string | null;
  cpe_enabled: boolean;
  cpe_match_confidence: number | null;
  cpe_match_method: string | null;
  security_identity: {
    status?: string;
    source?: string | null;
    ecosystem?: string;
    package?: string;
    version?: string | null;
  } | null;
  source: "manual" | "excel" | "scan" | "api";
  first_seen_at: string;
  last_seen_at: string;
  last_checked_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  active_vulnerability_count?: number;
};

export type ServiceInput = {
  name: string;
  version: string | null;
  category_id: string | null;
  vendor?: string | null;
  product?: string | null;
};

export type ServiceList = {
  items: Service[];
  total: number;
  page: number;
  page_size: number;
  vulnerable_total?: number;
  safe_total?: number;
  unverified_total?: number;
};

export function getCategories(
  platformId: string,
  signal?: AbortSignal,
  usedOnly = false,
): Promise<Category[]> {
  const suffix = usedOnly ? "?used_only=true" : "";
  return apiRequest<Category[]>(
    `/v1/platforms/${platformId}/categories${suffix}`,
    { signal },
    { authenticated: true },
  );
}

export type AICategorizationInput = {
  key: string;
  name: string;
  version?: string | null;
  vendor?: string | null;
  product?: string | null;
};

export type AICategorizationSuggestion = {
  key: string;
  category: Category;
  category_created: boolean;
  confidence: number;
  reason: string;
};

export function categorizeServices(
  platformId: string,
  items: AICategorizationInput[],
): Promise<{ items: AICategorizationSuggestion[] }> {
  return apiRequest(
    `/v1/platforms/${platformId}/categories/ai-categorize`,
    { method: "POST", body: JSON.stringify({ items }) },
    { authenticated: true },
  );
}

export type AICategorizationPreviewSuggestion = {
  key: string;
  category_name: string;
  existing_category_id: string | null;
  confidence: number;
  reason: string;
};

export function previewServiceCategorization(
  platformId: string,
  items: AICategorizationInput[],
): Promise<{ items: AICategorizationPreviewSuggestion[] }> {
  return apiRequest(
    `/v1/platforms/${platformId}/categories/ai-categorize/preview`,
    { method: "POST", body: JSON.stringify({ items }) },
    { authenticated: true },
  );
}

export function confirmServiceCategorization(
  platformId: string,
  items: { key: string; category_name: string; selected: boolean }[],
): Promise<{ items: { key: string; category: Category }[] }> {
  return apiRequest(
    `/v1/platforms/${platformId}/categories/ai-categorize/confirm`,
    { method: "POST", body: JSON.stringify({ items }) },
    { authenticated: true },
  );
}

export function createCategory(
  platformId: string,
  name: string,
): Promise<Category> {
  return apiRequest<Category>(
    `/v1/platforms/${platformId}/categories`,
    { method: "POST", body: JSON.stringify({ name }) },
    { authenticated: true },
  );
}

export function archiveCategory(categoryId: string): Promise<Category> {
  return apiRequest<Category>(
    `/v1/categories/${categoryId}`,
    { method: "DELETE" },
    { authenticated: true },
  );
}

export type ServiceFilters = {
  q?: string;
  category_id?: string;
  uncategorized?: boolean;
  page?: number;
  sort?:
    "name" | "-name" | "created_at" | "-created_at" | "version" | "-version";
  vulnerable?: boolean;
};

export function getServices(
  platformId: string,
  filters: ServiceFilters,
  signal?: AbortSignal,
): Promise<ServiceList> {
  const params = new URLSearchParams({
    page: String(filters.page ?? 1),
    page_size: "25",
    sort: filters.sort ?? "name",
  });
  if (filters.q) params.set("q", filters.q);
  if (filters.category_id) params.set("category_id", filters.category_id);
  if (filters.uncategorized) params.set("uncategorized", "true");
  if (filters.vulnerable !== undefined)
    params.set("vulnerable", String(filters.vulnerable));
  return apiRequest<ServiceList>(
    `/v1/platforms/${platformId}/services?${params}`,
    { signal },
    { authenticated: true },
  );
}

export function createServices(
  platformId: string,
  items: ServiceInput[],
): Promise<Service[]> {
  return apiRequest<Service[]>(
    `/v1/platforms/${platformId}/services/bulk`,
    { method: "POST", body: JSON.stringify({ items }) },
    { authenticated: true },
  );
}

export function getService(
  serviceId: string,
  signal?: AbortSignal,
): Promise<Service> {
  return apiRequest<Service>(
    `/v1/services/${serviceId}`,
    { signal },
    { authenticated: true },
  );
}

export function updateService(
  serviceId: string,
  input: ServiceInput,
): Promise<Service> {
  return apiRequest<Service>(
    `/v1/services/${serviceId}`,
    { method: "PATCH", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export function archiveService(serviceId: string): Promise<Service> {
  return apiRequest<Service>(
    `/v1/services/${serviceId}`,
    { method: "DELETE" },
    { authenticated: true },
  );
}

export type CpeCandidate = {
  id: string;
  cpe_uri: string;
  title: string | null;
  vendor: string | null;
  product: string | null;
  version: string | null;
  score: number;
  method: string;
  selected: boolean;
  last_checked_at: string;
};
export type ServiceVulnerability = {
  link_id: string;
  service_id: string;
  vulnerability_id: string;
  cve_id: string;
  title: string | null;
  description: string;
  severity: string | null;
  cvss_score: number | null;
  cvss_version: string | null;
  published_at: string | null;
  modified_at: string | null;
  match_state: string;
  match_reason: string;
  confidence: number;
  detected_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  ignored_at: string | null;
  ignore_reason: string | null;
};
export type VulnerabilityDetail = ServiceVulnerability & {
  source: string;
  metrics: Record<string, unknown>;
  weaknesses: unknown[];
  references: unknown[];
  affected_configuration: Record<string, unknown> | null;
  last_sync_at: string;
};
export type CheckResult = {
  status: string;
  source?: string | null;
  cpe_uri: string | null;
  candidates: number;
  active_vulnerabilities: number;
  new_notifications: number;
};

export type ManualVulnerabilityInput = {
  identifier?: string | null;
  title?: string | null;
  description: string;
  severity?: "critical" | "high" | "medium" | "low" | "unknown" | null;
  cvss_score?: number | null;
  reference_url?: string | null;
};

export function checkService(serviceId: string): Promise<CheckResult> {
  return apiRequest(
    `/v1/services/${serviceId}/check`,
    { method: "POST" },
    { authenticated: true },
  );
}
export function getCpeCandidates(
  serviceId: string,
  signal?: AbortSignal,
): Promise<CpeCandidate[]> {
  return apiRequest(
    `/v1/services/${serviceId}/cpe-candidates`,
    { signal },
    { authenticated: true },
  );
}
export function selectCpeCandidate(
  serviceId: string,
  candidateId: string,
): Promise<CpeCandidate> {
  return apiRequest(
    `/v1/services/${serviceId}/cpe-candidates/${candidateId}/select`,
    { method: "POST" },
    { authenticated: true },
  );
}
export function getServiceVulnerabilities(
  serviceId: string,
  signal?: AbortSignal,
  view: "active" | "history" = "active",
): Promise<ServiceVulnerability[]> {
  return apiRequest(
    `/v1/services/${serviceId}/vulnerabilities?view=${view}`,
    { signal },
    { authenticated: true },
  );
}

export function updateServiceCpe(
  serviceId: string,
  input: { enabled: boolean; cpe_uri?: string | null },
): Promise<Service> {
  return apiRequest(
    `/v1/services/${serviceId}/cpe`,
    { method: "PATCH", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export function createManualVulnerability(
  serviceId: string,
  input: ManualVulnerabilityInput,
): Promise<ServiceVulnerability> {
  return apiRequest(
    `/v1/services/${serviceId}/vulnerabilities/manual`,
    { method: "POST", body: JSON.stringify(input) },
    { authenticated: true },
  );
}
export function getVulnerability(
  linkId: string,
  signal?: AbortSignal,
): Promise<VulnerabilityDetail> {
  return apiRequest(
    `/v1/service-vulnerabilities/${linkId}`,
    { signal },
    { authenticated: true },
  );
}
export function setVulnerabilityIgnored(
  linkId: string,
  ignored: boolean,
  reason?: string,
): Promise<ServiceVulnerability> {
  return apiRequest(
    `/v1/service-vulnerabilities/${linkId}/ignore`,
    {
      method: "PATCH",
      body: JSON.stringify({ ignored, reason: reason || null }),
    },
    { authenticated: true },
  );
}
