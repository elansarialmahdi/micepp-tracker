import { Navigate } from "react-router";

import { landingPath } from "./access";
import { useAuth } from "./AuthProvider";

export function PermissionRoute({ permission, children }: { permission: string; children: React.ReactNode }) {
  const auth = useAuth();
  if (!auth.hasPermission(permission)) {
    return <Navigate to={landingPath(auth.user?.permissions)} replace />;
  }
  return children;
}
