import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from './AppRoutes';
import { PATHS } from './paths';
import { APP_ROUTES, currentRoute, isCurrentRoute, navLabel, routesFor } from './routes';
import { AUTHENTICATED, renderApp } from './test/utils';

/** Someone who is offered every section. */
const EVERYTHING = { ...AUTHENTICATED, functions: ['beheerder'] };

const titles = (functions: string[], relations: string[] = []) =>
  routesFor({ functions, relations }).map((route) => route.title);

describe('route table', () => {
  it('lists the sections in the order of the work, settings last', () => {
    expect(APP_ROUTES.map((route) => route.title)).toEqual([
      'Stand van zaken',
      'Taken',
      'Opdrachten',
      'Inzet',
      'Vacatures',
      'Team',
      'Kosten en facturen',
      'Factureren',
      'Rapportage',
      'Aanvragen',
      'Beheer',
    ]);
    expect(APP_ROUTES.filter((route) => route.area === 'settings').map((r) => r.title)).toEqual([
      'Beheer',
    ]);
  });

  it('offers each reader only the sections that can hold something for them', () => {
    const all = APP_ROUTES.map((route) => route.title);
    expect(titles(['beheerder'])).toEqual(all);
    // Owner or manager of assignments: the work and its money, no settings, no client role.
    expect(titles([], ['assignment_manager'])).toEqual([
      'Stand van zaken',
      'Taken',
      'Opdrachten',
      'Inzet',
      'Vacatures',
      'Team',
      'Kosten en facturen',
      'Factureren',
      'Rapportage',
    ]);
    expect(titles(['planner'])).toEqual([
      'Stand van zaken',
      'Taken',
      'Opdrachten',
      'Inzet',
      'Vacatures',
      'Team',
    ]);
    expect(titles([], ['line_manager'])).toEqual([
      'Stand van zaken',
      'Taken',
      'Inzet',
      'Vacatures',
      'Team',
    ]);
    expect(titles(['lezer'])).toEqual([
      'Stand van zaken',
      'Taken',
      'Opdrachten',
      'Vacatures',
      'Kosten en facturen',
      'Factureren',
      'Rapportage',
    ]);
    expect(titles([], ['team_member'])).toEqual([
      'Stand van zaken',
      'Taken',
      'Opdrachten',
      'Vacatures',
    ]);
    expect(titles(['aanvrager'])).toEqual(['Stand van zaken', 'Taken', 'Vacatures', 'Aanvragen']);
    expect(titles([])).toEqual(['Stand van zaken', 'Taken', 'Vacatures']);
  });

  it('knows which section a deeper page belongs to', () => {
    const section = (path: string) => currentRoute(path)?.title;
    expect(section('/')).toBe('Stand van zaken');
    expect(section('/opdrachten/a1/offerte')).toBe('Opdrachten');
    expect(section('/opdrachten/a1/geschiedenis')).toBe('Opdrachten');
    expect(section('/kosten/c1')).toBe('Kosten en facturen');
    expect(section('/team/p1')).toBe('Team');
    expect(section('/vacatures/open-rollen')).toBe('Vacatures');
    expect(section('/rapportage/opdrachten/a1')).toBe('Rapportage');
    expect(section('/aanvragen/offerte/q1')).toBe('Aanvragen');
    // Work that reaches you as a task.
    expect(section('/goedkeuren')).toBe('Taken');
    expect(section('/goedkeuren/q1')).toBe('Taken');
    // Reached from Beheer, whatever the address says.
    expect(section('/beheer/offertes')).toBe('Beheer');
    expect(section('/beheer/activiteit')).toBe('Beheer');
    expect(section('/vacatures/beheer')).toBe('Beheer');
    expect(section('/tarieven')).toBe('Beheer');
    expect(section('/bestaat-niet')).toBeUndefined();
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
  it.each(APP_ROUTES.map((route) => [route.title, route.path, navLabel(route)] as const))(
    'renders %s at %s with exactly one h1 and marks it current',
    (title, path, label) => {
      const { container } = renderApp(<AppRoutes />, { path, auth: EVERYTHING });

      const headings = screen.getAllByRole('heading', { level: 1 });
      expect(headings).toHaveLength(1);
      expect(headings[0]).toHaveTextContent(title);
      expect(document.title).toBe(`${title} · Testinstantie · grip`);

      const current = container.querySelectorAll('nldd-menu-bar-item[current]');
      expect(current).toHaveLength(1);
      expect(current[0]).toHaveAttribute('href', path);
      expect(current[0]).toHaveAttribute('text', label);
      // The narrow bars name the same section on their menu button.
      for (const button of container.querySelectorAll('nldd-button[start-icon="list"]')) {
        expect(button).toHaveAttribute('text', label);
      }
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
    expect(
      screen.getByRole('heading', { level: 1, name: 'Pagina niet gevonden' }),
    ).toBeInTheDocument();
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
