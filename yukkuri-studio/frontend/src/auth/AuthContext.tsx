import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { authApi } from "../api/auth";
import { ApiError, setUnauthorizedHandler } from "../api/client";
import type { User } from "../types";

interface AuthState {
  user: User | null;
  loading: boolean; // 起動時にログイン状態を確認している間
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authApi
      .me()
      .then(setUser)
      .catch((e) => {
        // 未ログイン(401)は普通の状態。サーバーに接続できない場合もログイン画面でエラーが分かるようにする
        if (!(e instanceof ApiError && e.status === 401)) console.error(e);
        setUser(null);
      })
      .finally(() => setLoading(false));
    // 操作中にログインが切れたら、ログイン画面へ戻す
    setUnauthorizedHandler(() => setUser(null));
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => setUser(await authApi.login(email, password)), []);
  const register = useCallback(async (email: string, password: string) => setUser(await authApi.register(email, password)), []);
  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null); // サーバーに届かなくても、画面上は必ずログアウトする
    }
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth は AuthProvider の中で使ってください");
  return ctx;
}
