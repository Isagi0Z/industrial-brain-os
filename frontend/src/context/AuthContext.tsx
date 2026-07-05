import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

interface AuthContextValue {
  token: string | null;
  refreshToken: string | null;
  setToken: (token: string | null) => void;
  setTokens: (access: string | null, refresh: string | null) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = 'ib_auth_token';
const REFRESH_KEY = 'ib_refresh_token';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [token, setTokenState] = useState<string | null>(() =>
    localStorage.getItem(TOKEN_KEY),
  );
  const [refreshToken, setRefreshTokenState] = useState<string | null>(() =>
    localStorage.getItem(REFRESH_KEY),
  );

  // Refs so the (install-once) fetch interceptor always reads the latest tokens.
  const tokenRef = useRef(token);
  const refreshRef = useRef(refreshToken);
  useEffect(() => {
    tokenRef.current = token;
  }, [token]);
  useEffect(() => {
    refreshRef.current = refreshToken;
  }, [refreshToken]);

  const setTokens = (access: string | null, refresh: string | null) => {
    tokenRef.current = access;
    refreshRef.current = refresh;
    if (access) localStorage.setItem(TOKEN_KEY, access);
    else localStorage.removeItem(TOKEN_KEY);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    else localStorage.removeItem(REFRESH_KEY);
    setTokenState(access);
    setRefreshTokenState(refresh);
  };

  const setToken = (value: string | null) =>
    setTokens(value, value ? refreshRef.current : null);
  const logout = () => setTokens(null, null);

  // Global auth: inject the bearer token on every /api/v1 request and
  // transparently refresh + retry once on a 401, so a session never dies with
  // "token validation failed". Installed once for the app's lifetime.
  useEffect(() => {
    const original = window.fetch;
    let refreshing: Promise<boolean> | null = null;

    const doRefresh = (): Promise<boolean> => {
      if (!refreshRef.current) return Promise.resolve(false);
      if (!refreshing) {
        const rt = refreshRef.current;
        refreshing = (async () => {
          try {
            const r = await original('/api/v1/auth/refresh', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh_token: rt }),
            });
            if (!r.ok) {
              setTokens(null, null);
              return false;
            }
            const d = await r.json();
            setTokens(d.access_token ?? null, d.refresh_token ?? null);
            return true;
          } catch {
            return false;
          } finally {
            refreshing = null;
          }
        })();
      }
      return refreshing;
    };

    const wrapped: typeof window.fetch = async (input, init) => {
      if (typeof input !== 'string') return original(input, init);
      const isApi =
        input.startsWith('/api/v1') && !input.startsWith('/api/v1/auth/');
      if (!isApi) return original(input, init);

      const withAuth = (opts?: RequestInit): RequestInit => {
        const headers = new Headers(opts?.headers || {});
        if (tokenRef.current)
          headers.set('Authorization', `Bearer ${tokenRef.current}`);
        return { ...opts, headers };
      };

      let resp = await original(input, withAuth(init));
      if (resp.status === 401 && refreshRef.current) {
        const ok = await doRefresh();
        if (ok) resp = await original(input, withAuth(init));
      }
      return resp;
    };

    window.fetch = wrapped;
    return () => {
      window.fetch = original;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthContext.Provider
      value={{ token, refreshToken, setToken, setTokens, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
};
