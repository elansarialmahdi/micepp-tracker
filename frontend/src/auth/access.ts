export function landingPath(permissions: string[] | undefined): string {
  if (permissions?.includes("dashboard.read")) return "/";
  if (permissions?.includes("treatment.read_own")) return "/my-treatments";
  if (permissions?.includes("history.read")) return "/activity";
  if (permissions?.includes("treatment.review")) return "/treatments";
  if (permissions?.includes("user.read")) return "/users";
  return "/change-password";
}
