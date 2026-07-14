import { apiRequest } from "./client";

export type RealtimeSettings = {
  enabled: boolean;
  interval_seconds: number;
  batch_size: number;
  max_concurrency: number;
  min_interval_seconds: number;
  last_run_at: string | null;
  next_run_at: string | null;
  updated_at: string;
};

export type ProtectionJob = {
  id: string;
  trigger: "manual" | "scheduled";
  status: "queued" | "running" | "succeeded" | "partial" | "failed" | "skipped";
  total_services: number;
  processed_services: number;
  succeeded_services: number;
  failed_services: number;
  new_notifications: number;
  current_batch: number;
  current_service_names?: string[];
  retry_count: number;
  error_summary: { code?: string; message?: string; service_id?: string }[];
  started_at: string | null;
  heartbeat_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export function getRealtimeSettings(signal?: AbortSignal): Promise<RealtimeSettings> {
  return apiRequest("/v1/settings/realtime-protection", { signal }, { authenticated: true });
}

export function updateRealtimeSettings(
  input: Partial<Pick<RealtimeSettings, "enabled" | "interval_seconds" | "batch_size" | "max_concurrency">>,
): Promise<RealtimeSettings> {
  return apiRequest("/v1/settings/realtime-protection", { method: "PATCH", body: JSON.stringify(input) }, { authenticated: true });
}

export function runRealtimeProtection(): Promise<ProtectionJob> {
  return apiRequest("/v1/settings/realtime-protection/run-now", { method: "POST" }, { authenticated: true });
}

export function getCurrentProtectionJob(signal?: AbortSignal): Promise<ProtectionJob | null> {
  return apiRequest("/v1/settings/realtime-protection/current-job", { signal }, { authenticated: true });
}
