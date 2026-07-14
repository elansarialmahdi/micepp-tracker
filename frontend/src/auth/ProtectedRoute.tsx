import { Navigate, Outlet, useLocation } from "react-router";

import { useAuth } from "./AuthProvider";

export function ProtectedRoute() {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === "loading") {
    return <p className="route-status" role="status">Chargement de la session…</p>;
  }
  if (auth.status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (auth.user?.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }
  return <Outlet />;
}

