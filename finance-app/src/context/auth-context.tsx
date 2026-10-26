import { createContext, type PropsWithChildren, useContext, useMemo, useState } from 'react';

import { api, type User } from '@/lib/api';

type AuthContextValue = {
  user: User | null;
  token: string | null;
  busy: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    token,
    busy,
    async login(email, password) {
      setBusy(true);
      try {
        const result = await api.login(email, password);
        setToken(result.token);
        setUser(result.user);
      } finally {
        setBusy(false);
      }
    },
    async register(name, email, password) {
      setBusy(true);
      try {
        await api.register(email, name, password);
        const result = await api.login(email, password);
        setToken(result.token);
        setUser(result.user);
      } finally {
        setBusy(false);
      }
    },
    async logout() {
      if (token) {
        try {
          await api.logout(token);
        } catch {
          // Clear local state even when the server is not reachable.
        }
      }
      setToken(null);
      setUser(null);
    },
  }), [busy, token, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
