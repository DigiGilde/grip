import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from './AppRoutes';
import { PATHS } from './paths';
import { APP_ROUTES, isCurrentRoute } from './routes';
import { renderApp } from './test/utils';

describe('route table', () => {
  it('lists the screens of the plan in navigation order', () => {
    expect(APP_ROUTES.map((route) => route.title)).toEqual([
      'Stand van zaken',
      'Taken',
      'Opdrachten',
      'Inzet',
      'Kosten en facturen',
      'Team',
      'Vacatures',
      'Rapportage',
      'Aanvragen',
      'Beheer',
    ]);
  });

  it('starts at Stand van zaken', () => {
    expect(APP_ROUTES[0]?.path).toBe('/');
  });

  it('has unique absolute paths that stay clear of the API', () => {
    const paths = APP_ROUTES.map((route) => route.path);
    expect(new Set(paths).size).toBe(paths.length);
    for (const path of paths) {
      expect(path.startsWith('/')).toBe(true);
      expect(path.startsWith('/api')).toBe(false);
    }
  });

  it('matches the start page exactly and the others by prefix', () => {
    expect(isCurrentRoute('/', '/')).toBe(true);
    expect(isCurrentRoute('/', '/opdrachten')).toBe(false);
    expect(isCurrentRoute('/opdrachten', '/opdrachten/123')).toBe(true);
    expect(isCurrentRoute('/team', '/teams')).toBe(false);
  });
});

describe('routes', () => {
  it.each(APP_ROUTES.map((route) => [route.title, route.path] as const))(
    'renders %s at %s with exactly one h1 and marks it current',
    (title, path) => {
      const { container } = renderApp(<AppRoutes />, { path });

      const headings = screen.getAllByRole('heading', { level: 1 });
      expect(headings).toHaveLength(1);
      expect(headings[0]).toHaveTextContent(title);
      expect(document.title).toBe(`${title} - Testinstantie`);

      const current = container.querySelectorAll('nldd-tab-bar-item[current]');
      expect(current.length).toBeGreaterThan(0);
      for (const item of current) expect(item).toHaveAttribute('href', path);
    },
  );

  it('offers a skip link to the main content', () => {
    const { container } = renderApp(<AppRoutes />);
    const skipLink = container.querySelector('nldd-skip-link');
    expect(skipLink).toHaveAttribute('href', '#inhoud');
    expect(container.querySelector('#inhoud')).not.toBeNull();
  });

  it('shows the instance name in the header', () => {
    const { container } = renderApp(<AppRoutes />);
    expect(container.querySelector('nldd-toolbar-title')).toHaveAttribute('text', 'Testinstantie');
  });

  it('renders a not-found page for an unknown path', () => {
    renderApp(<AppRoutes />, { path: '/bestaat-niet' });
    expect(screen.getByRole('heading', { level: 1, name: 'Pagina niet gevonden' })).toBeInTheDocument();
  });

  it('shows the login button to an unauthenticated visitor and starts login on click', () => {
    const login = vi.fn();
    const { container } = renderApp(<AppRoutes />, {
      path: '/opdrachten',
      auth: { status: 'unauthenticated', oidcConfigured: true },
      login,
    });

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    const button = container.querySelector('nldd-button');
    expect(button).toHaveAttribute('text', 'Inloggen met SSO Rijk');
    button?.dispatchEvent(new Event('click'));
    expect(login).toHaveBeenCalledOnce();
  });

  it('hides the login button when no identity provider is configured', () => {
    const { container } = renderApp(<AppRoutes />, {
      path: PATHS.login,
      auth: { status: 'unauthenticated', oidcConfigured: false },
    });
    expect(container.querySelector('nldd-button')).toBeNull();
    expect(container.querySelector('nldd-banner')).toHaveAttribute(
      'text',
      'Inloggen is op deze omgeving niet ingesteld.',
    );
  });

  it('shows the no-access page with a logout action to someone without a person record', () => {
    const logout = vi.fn();
    const { container } = renderApp(<AppRoutes />, {
      path: '/team',
      auth: { status: 'no-access' },
      logout,
    });

    expect(screen.getByRole('heading', { level: 1, name: 'Geen toegang' })).toBeInTheDocument();
    container.querySelector('nldd-button')?.dispatchEvent(new Event('click'));
    expect(logout).toHaveBeenCalledOnce();
  });

  it('sends an authenticated person away from the login page', () => {
    renderApp(<AppRoutes />, { path: PATHS.login });
    expect(screen.getByRole('heading', { level: 1, name: 'Stand van zaken' })).toBeInTheDocument();
  });
});
