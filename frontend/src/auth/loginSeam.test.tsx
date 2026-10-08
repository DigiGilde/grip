import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { loginUrl, parseLoginError, safeReturnPath } from '@/api/auth';
import { AppRoutes } from '@/AppRoutes';
import { LoginPage } from '@/pages/LoginPage';
import { PATHS } from '@/paths';
import { renderApp } from '@/test/utils';
import type { AuthState } from './context';

const ANONYMOUS: AuthState = { status: 'unauthenticated', oidcConfigured: true };

describe('return path', () => {
  it.each(['/opdrachten', '/tarieven?jaar=2026', '/team#top'])('accepts %s', (path) => {
    expect(safeReturnPath(path)).toBe(path);
  });

  it.each([
    '//evil.example',
    '/\\evil.example',
    'https://evil.example',
    'opdrachten',
    '/api/auth/logout',
    '/api',
    '',
    null,
    undefined,
    42,
  ])('rejects %s', (value) => {
    expect(safeReturnPath(value)).toBeNull();
  });

  it('sends the page to come back to as the next parameter', () => {
    expect(loginUrl('/tarieven?jaar=2026')).toBe('/api/auth/login?next=%2Ftarieven%3Fjaar%3D2026');
  });

  it('sends no next parameter for the start page or an unsafe value', () => {
    expect(loginUrl('/')).toBe('/api/auth/login');
    expect(loginUrl()).toBe('/api/auth/login');
    expect(loginUrl('//evil.example')).toBe('/api/auth/login');
  });
});

describe('login error from the backend', () => {
  it('knows the two values the backend sends and nothing else', () => {
    expect(parseLoginError('geen_toegang')).toBe('geen_toegang');
    expect(parseLoginError('mislukt')).toBe('mislukt');
    expect(parseLoginError('iets_anders')).toBeNull();
    expect(parseLoginError(null)).toBeNull();
  });

  it('shows the no-access page for geen_toegang, with a way to log out', () => {
    const logout = vi.fn();
    const { container } = renderApp(<AppRoutes />, {
      path: '/?login_error=geen_toegang',
      auth: ANONYMOUS,
      logout,
    });

    expect(screen.getByRole('heading', { level: 1, name: 'Geen toegang' })).toBeInTheDocument();
    container.querySelector('nldd-button')?.dispatchEvent(new Event('click'));
    expect(logout).toHaveBeenCalledOnce();
  });

  it('shows the login page with a message for mislukt', () => {
    const { container } = renderApp(<AppRoutes />, {
      path: '/?login_error=mislukt',
      auth: ANONYMOUS,
    });

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Inloggen bij');
    expect(container.querySelector('nldd-banner[variant="critical"]')).toHaveAttribute(
      'text',
      'Inloggen is mislukt.',
    );
    expect(container.querySelector('nldd-button')).toHaveAttribute('text', 'Inloggen met SSO Rijk');
  });

  it('ignores an unknown value and sends the visitor to a clean login page', () => {
    const { container } = renderApp(<AppRoutes />, {
      path: '/?login_error=iets_anders',
      auth: ANONYMOUS,
    });

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Inloggen bij');
    expect(container.querySelector('nldd-banner[variant="critical"]')).toBeNull();
  });

  it('does not show the no-access page to an anonymous visitor who just opens it', () => {
    renderApp(<AppRoutes />, { path: PATHS.noAccess, auth: ANONYMOUS });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Inloggen bij');
  });
});

describe('login page', () => {
  it('logs in with the page the guard sent the visitor away from', () => {
    const login = vi.fn();
    const { container } = renderApp(<LoginPage />, {
      path: { pathname: PATHS.login, state: { from: '/tarieven?jaar=2026' } },
      auth: ANONYMOUS,
      login,
    });

    container.querySelector('nldd-button')?.dispatchEvent(new Event('click'));
    expect(login).toHaveBeenCalledExactlyOnceWith('/tarieven?jaar=2026');
  });

  it('falls back to the start page when the remembered page is not a safe path', () => {
    const login = vi.fn();
    const { container } = renderApp(<LoginPage />, {
      path: { pathname: PATHS.login, state: { from: '//evil.example' } },
      auth: ANONYMOUS,
      login,
    });

    container.querySelector('nldd-button')?.dispatchEvent(new Event('click'));
    expect(login).toHaveBeenCalledExactlyOnceWith(PATHS.statusOverview);
  });
});
