import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext, type AuthContextValue, type AuthState } from '@/auth/context';
import { INSTANCE_KEY } from '@/layout/useInstance';

export const TEST_PERSON = { id: 'p-1', name: 'Testpersoon', email: 'test@example.org' };

export const AUTHENTICATED: AuthState = {
  status: 'authenticated',
  person: TEST_PERSON,
  functions: [],
};

interface RenderOptions {
  /** A path, or a location with router state (as a guard or redirect leaves it). */
  path?: string | { pathname: string; search?: string; state?: unknown };
  auth?: AuthState;
  login?: (next?: string) => void;
  logout?: () => void;
}

/** Renders inside a router, a fixed auth state and a query cache that never hits the network. */
export function renderApp(ui: ReactElement, options: RenderOptions = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData(INSTANCE_KEY, { name: 'Testinstantie', base_uri: 'https://grip.example' });

  const auth: AuthContextValue = {
    state: options.auth ?? AUTHENTICATED,
    login: options.login ?? (() => {}),
    logout: options.logout ?? (() => {}),
  };

  return render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={[options.path ?? '/']}>{ui}</MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}
