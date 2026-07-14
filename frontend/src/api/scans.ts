import { apiRequest } from "./client";

export type DetectedService = {
  id: string;
  detected_name: string;
  detected_version: string | null;
  detected_vendor: string | null;
  detected_product: string | null;
  detected_cpe: string | null;
  source_detector: string;
  confidence: number;
  port: number | null;
  protocol: string | null;
  category_suggestion: string | null;
  category_confidence: number | null;
  selected_for_import: boolean;
};

export type ScanJob = {
  id: string;
  platform_id: string | null;
  target: string;
  target_type: "url" | "ip";
  scan_type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  current_step: string;
  started_at: string | null;
  completed_at: string | null;
  error_code: string | null;
  sanitized_error: string | null;
  created_at: string;
  detections: DetectedService[];
};

export type ScanInput = {
  target?: string;
  scan_type: "full" | "ports" | "web";
};

export type ScanConfirmationItem = {
  detected_service_id: string;
  selected: boolean;
  name: string;
  version: string | null;
  category: string | null;
};

export function launchScan(platformId: string, input: ScanInput): Promise<ScanJob> {
  return apiRequest<ScanJob>(
    `/v1/platforms/${platformId}/scans`,
    { method: "POST", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export function getScan(scanId: string, signal?: AbortSignal): Promise<ScanJob> {
  return apiRequest<ScanJob>(`/v1/scans/${scanId}`, { signal }, { authenticated: true });
}

export function cancelScan(scanId: string): Promise<ScanJob> {
  return apiRequest<ScanJob>(`/v1/scans/${scanId}/cancel`, { method: "POST" }, { authenticated: true });
}

export function confirmScan(scanId: string, items: ScanConfirmationItem[]): Promise<{ created: number; skipped: number; categories_created: number }> {
  return apiRequest(
    `/v1/scans/${scanId}/confirm`,
    { method: "POST", body: JSON.stringify({ items }) },
    { authenticated: true },
  );
}
