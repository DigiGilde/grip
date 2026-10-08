import { useMemo, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchAuthStatus, LOGIN_URL, LOGOUT_URL } from '@/api/auth';
import { errorMessage } from '@/api/client';
import { AUTH_STATUS_KEY, toAuthState } from './authState';
import { AuthContext, type AuthContextValue, type AuthState } from './context';

// Login and logout are full-page navigations: the backend redirects to the
// identity provider and back, which a fetch cannot follow.
function login(): void {
  window.location.assign(LOGIN_URL);
}

function logout(): void {
  window.location.assign(LOGOUT_URL);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: AUTH_STATUS_KEY,
    queryFn: fetchAuthStatus,
    retry: false,
    staleTime: 60_000,
  });

  const { data, error, isPending, refetch } = query;

  const value = useMemo<AuthContextValue>(() => {
    let state: AuthState;
    if (data) state = toAuthState(data);
    else if (isPending) state = { status: 'loading' };
    else state = { status: 'error', message: errorMessage(error), retry: () => void refetch() };
    return { state, login, logout };
  }, [data, error, isPending, refetch]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
