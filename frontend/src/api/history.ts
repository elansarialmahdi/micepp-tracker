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
