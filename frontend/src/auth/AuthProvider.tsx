import { createContext, useContext, useEffect, useMemo, useState } from "react";

import {
  changePasswordRequest,
  loginRequest,
  logoutRequest,
  refreshRequest,
} from "../api/auth";
import { readCookie } from "../api/client";
import type { AuthUser, LoginValues } from "./types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

type AuthContextValue = {
  status: AuthStatus;
  user: AuthUser | null;
  login: (values: LoginValues) => Promise<AuthUser>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  hasPermission: (permission: string) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let active = true;
    if (!readCookie("micepp_csrf")) {
      setStatus("anonymous");
      return () => {
        active = false;
      };
    }
    void refreshRequest()
      .then((result) => {
        if (!active) return;
        setUser(result.user);
        setStatus("authenticated");
      })
      .catch(() => {
        if (!active) return;
        setUser(null);
        setStatus("anonymous");
      });
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login: async (values) => {
        const result = await loginRequest(values);
        setUser(result.user);
        setStatus("authenticated");
        return result.user;
      },
      logout: async () => {
        try {
          await logoutRequest();
        } finally {
          setUser(null);
          setStatus("anonymous");
        }
      },
      changePassword: async (currentPassword, newPassword) => {
        await changePasswordRequest(currentPassword, newPassword);
        setUser(null);
        setStatus("anonymous");
      },
      hasPermission: (permission) => user?.permissions.includes(permission) ?? false,
    }),
    [status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé dans AuthProvider.");
  return context;
}
