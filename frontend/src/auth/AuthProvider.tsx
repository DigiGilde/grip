import { useMemo, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchAuthStatus, loginUrl, LOGOUT_URL } from '@/api/auth';
import { errorMessage } from '@/api/client';
import { switchOff } from '@/features/notifications/api';
import { clearKeptFiles } from '@/pwa/serviceWorker';
import { AUTH_STATUS_KEY, toAuthState } from './authState';
import { AuthContext, type AuthContextValue, type AuthState } from './context';

// Login and logout are full-page navigations: the backend redirects to the
// identity provider and back, which a fetch cannot follow.
function login(next?: string): void {
  window.location.assign(loginUrl(next));
}

function logout(): void {
  // Nothing of this session's shell stays behind on a shared device.
  // Whoever logs out leaves this device: it gets no notifications after.
  void switchOff()
    .catch(() => undefined)
    .then(clearKeptFiles)
    .finally(() => window.location.assign(LOGOUT_URL));
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
