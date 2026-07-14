import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";

import { queryClient } from "./app/queryClient";
import { AuthProvider } from "./auth/AuthProvider";
import { router } from "./routes/router";
import "./styles/global.css";
import "./styles/micepp-theme.css";

const savedTheme = window.localStorage.getItem("micepp-theme");
document.documentElement.dataset.theme = savedTheme === "light" ? "light" : "dark";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("L’élément racine de l’application est introuvable.");
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
