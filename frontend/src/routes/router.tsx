import { createBrowserRouter } from "react-router";

import { ProtectedRoute } from "../auth/ProtectedRoute";
import { AppLayout } from "../layouts/AppLayout";
import { ChangePasswordPage } from "../pages/ChangePasswordPage";
import { DashboardPage } from "../pages/DashboardPage";
import { LoginPage } from "../pages/LoginPage";
import { PlatformDetailPage } from "../pages/PlatformDetailPage";
import { PlatformsPage } from "../pages/PlatformsPage";
import { ServiceDetailPage } from "../pages/ServiceDetailPage";
import { SettingsPage } from "../pages/SettingsPage";
import { NotificationsPage } from "../pages/NotificationsPage";
import { VulnerabilityDetailPage } from "../pages/VulnerabilityDetailPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/change-password", element: <ChangePasswordPage /> },
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <DashboardPage /> },
          { path: "/platforms", element: <PlatformsPage /> },
          { path: "/platforms/:platformId", element: <PlatformDetailPage /> },
          { path: "/services/:serviceId", element: <ServiceDetailPage /> },
          {
            path: "/vulnerabilities/:linkId",
            element: <VulnerabilityDetailPage />,
          },
          { path: "/notifications", element: <NotificationsPage /> },
          { path: "/settings", element: <SettingsPage /> },
          {
            path: "/activity",
            element: <PlaceholderPage title="Historique des activités" />,
          },
          {
            path: "/users",
            element: <PlaceholderPage title="Utilisateurs et permissions" />,
          },
        ],
      },
    ],
  },
]);
