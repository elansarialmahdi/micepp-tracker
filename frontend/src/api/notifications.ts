import { apiRequest } from "./client";

export type NotificationItem = {
  id: string;
  type: string;
  title: string;
  message: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  vulnerability_id: string | null;
  service_id: string | null;
  service_name: string | null;
  service_version: string | null;
  threat_identifier: string | null;
  platform_ids: string[];
  platforms: Array<{ id: string; name: string }>;
  created_at: string;
  read_at: string | null;
  is_read: boolean;
  metadata: Record<string, unknown>;
};

export type NotificationList = {
  items: NotificationItem[];
  total: number;
  page: number;
  page_size: number;
};

export function getNotifications(signal?: AbortSignal, hidden = false): Promise<NotificationList> {
  return apiRequest<NotificationList>(
    `/v1/notifications${hidden ? "?hidden=true" : ""}`,
    { signal },
    { authenticated: true },
  );
}

export function readNotification(id: string): Promise<NotificationItem> {
  return apiRequest<NotificationItem>(
    `/v1/notifications/${id}/read`,
    { method: "POST" },
    { authenticated: true },
  );
}

export function hideNotification(id: string): Promise<void> {
  return apiRequest(`/v1/notifications/${id}/hide`, { method: "POST" }, { authenticated: true });
}

export function hideAllNotifications(): Promise<void> {
  return apiRequest("/v1/notifications/hide-all", { method: "POST" }, { authenticated: true });
}
