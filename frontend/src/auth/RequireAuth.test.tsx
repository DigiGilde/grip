import { screen } from '@testing-library/react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { AUTHENTICATED, renderApp } from '@/test/utils';
import { toAuthState } from './authState';
import type { AuthState } from './context';
import { RequireAuth, RequireSigner } from './RequireAuth';

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
    expect(
      screen.getByRole('heading', { level: 1, name: 'Grip wordt geladen' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();
  });

  it('shows the error and no content when the status request failed', () => {
    const retry = vi.fn();
    const { container } = renderGuarded({
      status: 'error',
      message: 'Server onbereikbaar.',
      retry,
    });
    expect(
      screen.getByRole('heading', { level: 1, name: 'Grip is niet bereikbaar' }),
    ).toBeInTheDocument();
    expect(container.querySelector('nldd-inline-dialog')).toHaveAttribute(
      'text',
      'Server onbereikbaar.',
    );
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

const GUEST: AuthState = {
  status: 'guest',
  guest: { name: 'Gast Tekenaar', email: 'gast@opdrachtgever.example' },
};

function renderWithSigning(auth: AuthState, path: string) {
  return renderApp(
    <Routes>
      <Route path={PATHS.login} element={<LoginProbe />} />
      <Route path={PATHS.noAccess} element={<p>no access</p>} />
      <Route
        path={PATHS.signing}
        element={
          <RequireSigner>
            <p>signing page</p>
          </RequireSigner>
        }
      />
      <Route
        path={PATHS.signingQuote}
        element={
          <RequireSigner>
            <p>one quote</p>
          </RequireSigner>
        }
      />
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

describe('an invited signer without a person record', () => {
  it('is a state of its own, apart from logged out and from a person', () => {
    expect(
      toAuthState({
        authenticated: false,
        oidc_configured: true,
        person: null,
        functions: [],
        guest: { name: 'Gast Tekenaar', email: 'gast@opdrachtgever.example' },
      }),
    ).toEqual(GUEST);
    expect(
      toAuthState({
        authenticated: false,
        oidc_configured: true,
        person: null,
        functions: [],
        guest: null,
      }),
    ).toEqual({ status: 'unauthenticated', oidcConfigured: true });
  });

  it('reaches the signing pages', () => {
    renderWithSigning(GUEST, '/tekenen');
    expect(screen.getByText('signing page')).toBeInTheDocument();
  });

  it('reaches the quote a signing link points at', () => {
    renderWithSigning(GUEST, '/tekenen/q-1');
    expect(screen.getByText('one quote')).toBeInTheDocument();
  });

  it.each(['/', '/opdrachten', '/team', '/vacatures/beheer', '/bestaat-niet'])(
    'lands on the signing page from %s, never in the application',
    (path) => {
      renderWithSigning(GUEST, path);
      expect(screen.getByText('signing page')).toBeInTheDocument();
      expect(screen.queryByText('protected content')).not.toBeInTheDocument();
    },
  );

  it('lets a person of the instance sign too', () => {
    renderWithSigning(AUTHENTICATED, '/tekenen');
    expect(screen.getByText('signing page')).toBeInTheDocument();
  });

  it('sends a visitor who is not logged in to login, remembering the signing link', () => {
    renderWithSigning({ status: 'unauthenticated', oidcConfigured: true }, '/tekenen/q-1');
    expect(screen.getByText('login, from /tekenen/q-1')).toBeInTheDocument();
  });

  it('keeps someone without an invitation out of the signing pages', () => {
    renderWithSigning({ status: 'no-access' }, '/tekenen');
    expect(screen.getByText('no access')).toBeInTheDocument();
  });
});
