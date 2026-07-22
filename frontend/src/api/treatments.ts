import { apiRequest } from "./client";

export type TreatmentUser = {
  id: string;
  username: string;
  display_name: string;
};

export type Treatment = {
  id: string;
  status: "assigned" | "submitted" | "confirmed" | "cancelled";
  assignment_note: string | null;
  completion_note: string | null;
  service_version_before: string | null;
  new_version: string | null;
  assigned_at: string;
  submitted_at: string | null;
  confirmed_at: string | null;
  service_id: string;
  service_name: string;
  service_version: string | null;
  platform_id: string;
  platform_name: string;
  assignee: TreatmentUser | null;
  assigned_by: TreatmentUser | null;
  confirmed_by: TreatmentUser | null;
};

export function getTreatmentAssignees(signal?: AbortSignal): Promise<TreatmentUser[]> {
  return apiRequest("/v1/treatment-assignees", { signal }, { authenticated: true });
}

export function createTreatment(input: {
  service_id: string;
  assigned_to_id: string;
  note?: string | null;
}): Promise<Treatment> {
  return apiRequest(
    "/v1/treatments",
    { method: "POST", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export function getMyTreatments(signal?: AbortSignal, state: "open" | "all" = "open"): Promise<Treatment[]> {
  return apiRequest(`/v1/treatments/mine?state=${state}`, { signal }, { authenticated: true });
}

export function getTreatments(
  signal?: AbortSignal,
  state: "open" | "all" | "submitted" | "confirmed" | "cancelled" = "open",
): Promise<Treatment[]> {
  return apiRequest(`/v1/treatments?state=${state}`, { signal }, { authenticated: true });
}

export function submitTreatment(
  treatmentId: string,
  input: { new_version: string; note?: string | null },
): Promise<Treatment> {
  return apiRequest(
    `/v1/treatments/${treatmentId}/submit`,
    { method: "PATCH", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export function confirmTreatment(treatmentId: string): Promise<Treatment> {
  return apiRequest(
    `/v1/treatments/${treatmentId}/confirm`,
    { method: "PATCH" },
    { authenticated: true },
  );
}

export function cancelTreatment(treatmentId: string): Promise<Treatment> {
  return apiRequest(
    `/v1/treatments/${treatmentId}/cancel`,
    { method: "PATCH" },
    { authenticated: true },
  );
}
