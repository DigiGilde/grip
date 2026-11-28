import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthContext } from '@/auth/context';
import { AUTH_STATUS_KEY } from '@/auth/authState';
import { AUTHENTICATED } from '@/test/utils';
import { MePage } from './MePage';
import { INSTANCE_KEY } from './useInstance';

function renderMe({ example }: { example: boolean }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData(INSTANCE_KEY, {
    name: 'Voorbeeldgilde, grip',
    base_uri: 'https://grip.example',
    example,
  });
  // The server names a visitor only on an example instance.
  queryClient.setQueryData(AUTH_STATUS_KEY, {
    ...(example ? { example_visitor: 'Fenna Fictief' } : {}),
    person: { id: 'p-1', name: 'Priya Product' },
  });
  queryClient.setQueryData(['example-persons'], []);
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={{ state: AUTHENTICATED, login: () => {}, logout: () => {} }}>
        <MemoryRouter>
          <MePage />
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}

describe('MePage', () => {
  it('says as whom a visitor of an example looks and as whom they logged in', () => {
    const { container } = renderMe({ example: true });
    expect(container.textContent).toContain(
      'Je kijkt als Priya Product, ingelogd als Fenna Fictief',
    );
  });

  it('says nothing of the kind on an instance for real work', () => {
    const { container } = renderMe({ example: false });
    expect(container.textContent).not.toContain('ingelogd als');
  });
});
