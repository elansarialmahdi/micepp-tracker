import { apiRequest } from "./client";

export type AuditEvent = {
  id: string;
  actor_user_id: string | null;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  platform_id: string | null;
  summary: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  ip: string | null;
  request_id: string | null;
  created_at: string;
};

export type AuditEventList = {
  items: AuditEvent[];
  total: number;
  page: number;
  page_size: number;
  success_total: number;
  failure_total: number;
};

export type ActivityResult = "all" | "success" | "failure";

export type ActivityHistoryFilters = {
  q?: string;
  result?: ActivityResult;
  page?: number;
  pageSize?: number;
};

export function getPlatformHistory(platformId: string, signal?: AbortSignal, hidden = false): Promise<AuditEventList> {
  return apiRequest<AuditEventList>(
    `/v1/platforms/${platformId}/history${hidden ? "?hidden=true" : ""}`,
    { signal },
    { authenticated: true },
  );
}

export function hidePlatformHistory(platformId: string): Promise<void> {
  return apiRequest(
    `/v1/platforms/${platformId}/history/hide`,
    { method: "POST" },
    { authenticated: true },
  );
}

export function getActivityHistory(
  filters: ActivityHistoryFilters = {},
  signal?: AbortSignal,
): Promise<AuditEventList> {
  const params = new URLSearchParams({
    page: String(filters.page ?? 1),
    page_size: String(filters.pageSize ?? 50),
    result: filters.result ?? "all",
  });
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  return apiRequest<AuditEventList>(
    `/v1/activity?${params.toString()}`,
    { signal },
    { authenticated: true },
  );
}

export function clearActivityHistory(): Promise<void> {
  return apiRequest(
    "/v1/activity/hide",
    { method: "POST" },
    { authenticated: true },
  );
}

export function trackPageView(path: string, title: string): Promise<void> {
  return apiRequest(
    "/v1/activity/page-view",
    {
      method: "POST",
      body: JSON.stringify({ path, title }),
    },
    { authenticated: true },
  );
}
