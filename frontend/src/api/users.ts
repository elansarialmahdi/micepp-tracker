import { apiRequest } from "./client";

export type ManagedRole = {
  id: string;
  name: string;
  description: string | null;
  permissions: string[];
};

export type ManagedUser = {
  id: string;
  username: string;
  display_name: string;
  is_active: boolean;
  must_change_password: boolean;
  roles: ManagedRole[];
  last_login_at: string | null;
  created_at: string;
};

export function getManagedUsers(signal?: AbortSignal): Promise<ManagedUser[]> {
  return apiRequest("/v1/users", { signal }, { authenticated: true });
}

export function getRoles(signal?: AbortSignal): Promise<ManagedRole[]> {
  return apiRequest("/v1/roles", { signal }, { authenticated: true });
}

export function createManagedUser(input: {
  username: string;
  password: string;
  role_ids: string[];
}): Promise<ManagedUser> {
  return apiRequest(
    "/v1/users",
    { method: "POST", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export function updateManagedUser(
  userId: string,
  input: { username: string; role_ids: string[] },
): Promise<ManagedUser> {
  return apiRequest(
    `/v1/users/${userId}`,
    { method: "PATCH", body: JSON.stringify(input) },
    { authenticated: true },
  );
}

export function updateManagedUserPassword(userId: string, password: string): Promise<{ message: string }> {
  return apiRequest(
    `/v1/users/${userId}/password`,
    { method: "PATCH", body: JSON.stringify({ password }) },
    { authenticated: true },
  );
}

export function archiveManagedUser(userId: string): Promise<void> {
  return apiRequest(
    `/v1/users/${userId}`,
    { method: "DELETE" },
    { authenticated: true },
  );
}
