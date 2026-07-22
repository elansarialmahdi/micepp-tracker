import { createBrowserRouter } from "react-router";

import { ProtectedRoute } from "../auth/ProtectedRoute";
import { PermissionRoute } from "../auth/PermissionRoute";
import { AppLayout } from "../layouts/AppLayout";
import { ChangePasswordPage } from "../pages/ChangePasswordPage";
import { ActivityPage } from "../pages/ActivityPage";
import { AdminTreatmentsPage, MyTreatmentsPage } from "../pages/TreatmentsPage";
import { DashboardPage } from "../pages/DashboardPage";
import { LoginPage } from "../pages/LoginPage";
import { PlatformDetailPage } from "../pages/PlatformDetailPage";
import { PlatformsPage } from "../pages/PlatformsPage";
import { ServiceDetailPage } from "../pages/ServiceDetailPage";
import { SettingsPage } from "../pages/SettingsPage";
import { NotificationsPage } from "../pages/NotificationsPage";
import { VulnerabilityDetailPage } from "../pages/VulnerabilityDetailPage";
import { UsersPage } from "../pages/UsersPage";

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
          { path: "/", element: <PermissionRoute permission="dashboard.read"><DashboardPage /></PermissionRoute> },
          { path: "/platforms", element: <PermissionRoute permission="platform.read"><PlatformsPage /></PermissionRoute> },
          { path: "/platforms/:platformId", element: <PermissionRoute permission="platform.read"><PlatformDetailPage /></PermissionRoute> },
          { path: "/services/:serviceId", element: <PermissionRoute permission="service.read"><ServiceDetailPage /></PermissionRoute> },
          {
            path: "/vulnerabilities/:linkId",
            element: <PermissionRoute permission="service.read"><VulnerabilityDetailPage /></PermissionRoute>,
          },
          { path: "/notifications", element: <PermissionRoute permission="notification.read"><NotificationsPage /></PermissionRoute> },
          { path: "/settings", element: <PermissionRoute permission="settings.read"><SettingsPage /></PermissionRoute> },
          {
            path: "/activity",
            element: <PermissionRoute permission="history.read"><ActivityPage /></PermissionRoute>,
          },
          {
            path: "/users",
            element: <PermissionRoute permission="user.read"><UsersPage /></PermissionRoute>,
          },
          { path: "/my-treatments", element: <PermissionRoute permission="treatment.read_own"><MyTreatmentsPage /></PermissionRoute> },
          { path: "/treatments", element: <PermissionRoute permission="treatment.review"><AdminTreatmentsPage /></PermissionRoute> },
        ],
      },
    ],
  },
]);
