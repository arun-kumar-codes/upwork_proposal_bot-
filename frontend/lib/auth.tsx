"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { API_URL, TOKEN_KEY, getToken } from "./api";

interface AuthCtx {
  token: string | null;
  ready: boolean;
  login: (password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>({
  token: null,
  ready: false,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const existing = getToken();
    if (!existing) {
      setReady(true);
      return;
    }
    fetch(`${API_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${existing}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error("invalid");
        setToken(existing);
      })
      .catch(() => window.localStorage.removeItem(TOKEN_KEY))
      .finally(() => setReady(true));
  }, []);

  const login = useCallback(async (password: string) => {
    const resp = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!resp.ok) throw new Error("Invalid password");
    const data = await resp.json();
    window.localStorage.setItem(TOKEN_KEY, data.token);
    setToken(data.token);
  }, []);

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    router.push("/login");
  }, [router]);

  return (
    <Ctx.Provider value={{ token, ready, login, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  return useContext(Ctx);
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { token, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);
  if (!ready || !token) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }
  return <>{children}</>;
}
