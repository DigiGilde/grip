import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AuthState } from '@/auth/context';
import { PATHS } from '@/paths';
import { renderApp } from '@/test/utils';
import { LoginPage } from './LoginPage';

const ANONYMOUS: AuthState = { status: 'unauthenticated', oidcConfigured: true };

describe('LoginPage', () => {
  it('says the visitor logs in to sign, with the organisation they work for', () => {
    const { container } = renderApp(<LoginPage />, {
      path: { pathname: PATHS.login, state: { from: '/tekenen/q-1' } },
      auth: ANONYMOUS,
    });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Inloggen om de offerte te tekenen',
    );
    expect(container.textContent).toContain('met de organisatie waar je werkt');
    expect(container.textContent).not.toContain('Inloggen bij');
  });

  it('keeps the usual login for any other page', () => {
    renderApp(<LoginPage />, {
      path: { pathname: PATHS.login, state: { from: '/opdrachten' } },
      auth: ANONYMOUS,
    });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Inloggen bij');
  });
});
