import { screen } from '@testing-library/react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { AUTHENTICATED, renderApp } from '@/test/utils';
import { toAuthState } from './authState';
import type { AuthState } from './context';
import { RequireAuth } from './RequireAuth';

function LoginProbe() {
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  return <p>login, from {from}</p>;
}

function renderGuarded(auth: AuthState, path = '/opdrachten') {
  return renderApp(
    <Routes>
      <Route path={PATHS.login} element={<LoginProbe />} />
      <Route path={PATHS.noAccess} element={<p>no access</p>} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <p>protected content</p>
          </RequireAuth>
        }
      />
    </Routes>,
    { auth, path },
  );
}

describe('RequireAuth', () => {
  it('renders its children for an authenticated person', () => {
    renderGuarded(AUTHENTICATED);
    expect(screen.getByText('protected content')).toBeInTheDocument();
  });

  it('sends an unauthenticated visitor to login and remembers where they were', () => {
    renderGuarded({ status: 'unauthenticated', oidcConfigured: true }, '/tarieven');
    expect(screen.getByText('login, from /tarieven')).toBeInTheDocument();
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();
  });

  it('sends someone without a person record to the no-access page', () => {
    renderGuarded({ status: 'no-access' });
    expect(screen.getByText('no access')).toBeInTheDocument();
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();
  });

  it('shows a loading page and no content while the status is unknown', () => {
    renderGuarded({ status: 'loading' });
    expect(screen.getByRole('heading', { level: 1, name: 'Grip wordt geladen' })).toBeInTheDocument();
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();
  });

  it('shows the error and no content when the status request failed', () => {
    const retry = vi.fn();
    const { container } = renderGuarded({ status: 'error', message: 'Server onbereikbaar.', retry });
    expect(screen.getByRole('heading', { level: 1, name: 'Grip is niet bereikbaar' })).toBeInTheDocument();
    expect(container.querySelector('nldd-inline-dialog')).toHaveAttribute('text', 'Server onbereikbaar.');
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();

    container.querySelector('nldd-button')?.dispatchEvent(new Event('click'));
    expect(retry).toHaveBeenCalledOnce();
  });
});

describe('toAuthState', () => {
  const person = { id: 'p-1', name: 'Testpersoon', email: 'test@example.org' };

  it('maps an anonymous status to unauthenticated', () => {
    expect(
      toAuthState({ authenticated: false, oidc_configured: true, person: null, functions: [] }),
    ).toEqual({ status: 'unauthenticated', oidcConfigured: true });
  });

  it('maps an authenticated status without a person to no-access', () => {
    expect(
      toAuthState({ authenticated: true, oidc_configured: true, person: null, functions: [] }),
    ).toEqual({ status: 'no-access' });
  });

  it('maps an authenticated status with a person to authenticated', () => {
    expect(
      toAuthState({ authenticated: true, oidc_configured: true, person, functions: ['planner'] }),
    ).toEqual({ status: 'authenticated', person, functions: ['planner'] });
  });
});
