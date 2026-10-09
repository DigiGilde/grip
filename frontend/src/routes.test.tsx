import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from './AppRoutes';
import { PATHS } from './paths';
import {
  APP_ROUTES,
  currentRoute,
  currentView,
  isCurrentRoute,
  landingPath,
  navLabel,
  routesFor,
} from './routes';
import { AUTHENTICATED, renderApp } from './test/utils';

/** Someone who is offered every section. */
const EVERYTHING = { ...AUTHENTICATED, functions: ['beheerder'] };
const PLANNER = { ...AUTHENTICATED, functions: ['planner'] };

describe('route table', () => {
  it('lists seven places for the work, the client role and the settings last', () => {
    expect(APP_ROUTES.map(navLabel)).toEqual([
      'Start',
      'Taken',
      'Opdrachten',
      'Team',
      'Vacatures',
      'Financieel',
      'Rapportage',
      'Aanvragen',
      'Beheer',
    ]);
    expect(APP_ROUTES.filter((route) => route.area === 'settings').map((r) => r.title)).toEqual([
      'Beheer',
    ]);
    // Two pages about one thing share a section and stand side by side.
    const views = (label: string) =>
      APP_ROUTES.find((route) => navLabel(route) === label)?.views?.map((view) => view.title);
    expect(views('Team')).toEqual(['Mensen', 'Inzet']);
    expect(views('Financieel')).toEqual(['Kosten', 'Factureren']);
  });

  it('offers each reader only the sections that can hold something for them', () => {
    const labels = (functions: string[], relations: string[] = []) =>
      routesFor({ functions, relations }).map(navLabel);
    // The role of client is for who holds it; a beheerder reaches it from Beheer.
    expect(labels(['beheerder'])).toEqual([
      'Start',
      'Taken',
      'Opdrachten',
      'Team',
      'Vacatures',
      'Financieel',
      'Rapportage',
      'Beheer',
    ]);
    // Owner or manager of assignments: the work and its money, no settings, no client role.
    expect(labels([], ['assignment_manager'])).toEqual([
      'Start',
      'Taken',
      'Opdrachten',
      'Team',
      'Vacatures',
      'Financieel',
      'Rapportage',
    ]);
    expect(labels(['planner'])).toEqual(['Start', 'Taken', 'Opdrachten', 'Team', 'Vacatures']);
    expect(labels([], ['line_manager'])).toEqual(['Start', 'Taken', 'Team', 'Vacatures']);
    expect(labels(['lezer'])).toEqual([
      'Start',
      'Taken',
      'Opdrachten',
      'Vacatures',
      'Financieel',
      'Rapportage',
    ]);
    expect(labels([], ['team_member'])).toEqual(['Start', 'Taken', 'Opdrachten', 'Vacatures']);
    expect(labels(['aanvrager'])).toEqual(['Start', 'Taken', 'Vacatures', 'Aanvragen']);
    expect(labels(['tekenbevoegde'])).toEqual(['Start', 'Taken', 'Vacatures', 'Aanvragen']);
    expect(labels([])).toEqual(['Start', 'Taken', 'Vacatures']);
    // No reader is offered more than seven places for the work.
    for (const viewer of [
      { functions: ['beheerder'], relations: ['assignment_manager', 'line_manager'] },
      { functions: ['planner', 'lezer'], relations: ['assignment_manager', 'team_member'] },
    ]) {
      expect(routesFor(viewer, 'work').length).toBeLessThanOrEqual(7);
    }
  });

  it("opens a section on the view that is the reader's own", () => {
    const team = APP_ROUTES.find((route) => route.title === 'Team')!;
    const money = APP_ROUTES.find((route) => route.title === 'Financieel')!;
    const start = APP_ROUTES[0]!;
    // The board is where a planner works; everyone else starts with the people.
    expect(landingPath(team, { functions: ['planner'], relations: [] })).toBe('/inzet');
    expect(landingPath(team, { functions: [], relations: ['line_manager'] })).toBe('/team');
    expect(landingPath(team, { functions: ['beheerder'], relations: [] })).toBe('/team');
    expect(landingPath(money, { functions: ['lezer'], relations: [] })).toBe('/kosten');
    expect(landingPath(start, { functions: [], relations: [] })).toBe('/');
  });

  it('keeps the view of a deeper page', () => {
    const view = (path: string) => {
      const section = currentRoute(path);
      return section ? currentView(section, path)?.title : undefined;
    };
    expect(view('/team')).toBe('Mensen');
    expect(view('/team/p1')).toBe('Mensen');
    expect(view('/inzet')).toBe('Inzet');
    expect(view('/kosten/c1')).toBe('Kosten');
    expect(view('/factureren')).toBe('Factureren');
    expect(view('/factureren/d1')).toBe('Factureren');
    expect(view('/opdrachten/a1')).toBeUndefined();
  });

  it('knows which section a deeper page belongs to', () => {
    const section = (path: string) => currentRoute(path)?.title;
    expect(section('/')).toBe('Stand van zaken');
    expect(section('/opdrachten/a1/offerte')).toBe('Opdrachten');
    expect(section('/opdrachten/a1/geschiedenis')).toBe('Opdrachten');
    expect(section('/kosten/c1')).toBe('Financieel');
    expect(section('/factureren/d1')).toBe('Financieel');
    expect(section('/team/p1')).toBe('Team');
    expect(section('/inzet')).toBe('Team');
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
    const paths = APP_ROUTES.flatMap((route) =>
      route.views ? route.views.map((view) => view.path) : [route.path],
    );
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
  /** The heading each page of the first level carries, by address. */
  const HEADINGS: Record<string, string> = {
    '/': 'Stand van zaken',
    '/taken': 'Taken',
    '/opdrachten': 'Opdrachten',
    '/team': 'Team',
    '/inzet': 'Inzet',
    '/vacatures': 'Vacatures',
    '/kosten': 'Kosten en facturen',
    '/factureren': 'Factureren',
    '/rapportage': 'Rapportage',
    '/aanvragen': 'Aanvragen',
    '/beheer': 'Beheer',
  };
  /** Someone who is offered every section, the role of client included. */
  const ALL = { ...AUTHENTICATED, functions: ['beheerder', 'aanvrager'] };
  const PAGES = APP_ROUTES.flatMap((route) =>
    (route.views ?? [{ path: route.path, title: undefined }]).map(
      (view) => [view.path, navLabel(route), view.title] as const,
    ),
  );

  it.each(PAGES)(
    'renders %s with exactly one h1, marks %s current and its view %s',
    async (path, label, view) => {
      const { container } = renderApp(<AppRoutes />, { path, auth: ALL });

      // Most pages are a file of their own: wait for it.
      const headings = await screen.findAllByRole('heading', { level: 1 });
      expect(headings).toHaveLength(1);
      expect(headings[0]).toHaveTextContent(HEADINGS[path]!);
      expect(document.title).toBe(`${HEADINGS[path]} · Testinstantie · grip`);

      const current = container.querySelectorAll('.main-navigation nldd-menu-bar-item[current]');
      expect(current).toHaveLength(1);
      expect(current[0]).toHaveAttribute('text', label);
      // The narrow bars name the same section on their menu button.
      for (const button of container.querySelectorAll('nldd-button[start-icon="list"]')) {
        expect(button).toHaveAttribute('text', label);
      }

      // The second bar: only for a section of more than one page, as links
      // in a named navigation region, the page you are on marked. The same
      // kind of bar as the main one, so nothing in it is a filled mark.
      const second = container.querySelector('.section-views nldd-menu-bar');
      if (view === undefined) {
        expect(second).toBeNull();
        return;
      }
      expect(second).toHaveAttribute('accessible-label', `Pagina's van ${label}`);
      const marked = second!.querySelectorAll('nldd-menu-bar-item[current]');
      expect(marked).toHaveLength(1);
      expect(marked[0]).toHaveAttribute('text', view);
      expect(marked[0]).toHaveAttribute('href', path);
    },
  );

  it('keeps every address that left the bar', async () => {
    // A page has its address whether or not the navigation names it.
    for (const path of ['/inzet', '/kosten', '/factureren', '/aanvragen']) {
      const { unmount } = renderApp(<AppRoutes />, { path, auth: EVERYTHING });
      expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(HEADINGS[path]!);
      unmount();
    }
  });

  it('keeps the section and the view on a deeper page', () => {
    const { container } = renderApp(<AppRoutes />, { path: '/team/p1', auth: EVERYTHING });
    expect(container.querySelector('.main-navigation nldd-menu-bar-item[current]')).toHaveAttribute(
      'text',
      'Team',
    );
    expect(container.querySelector('.section-views nldd-menu-bar-item[current]')).toHaveAttribute(
      'text',
      'Mensen',
    );
  });

  it('sends a planner to the board and lists the views in the narrow menu', () => {
    const { container } = renderApp(<AppRoutes />, {
      path: '/opdrachten',
      auth: PLANNER,
    });
    expect(
      container.querySelector('.main-navigation nldd-menu-bar-item[text="Team"]'),
    ).toHaveAttribute('href', '/inzet');
    const menu = container.querySelector('.navigation-menu-button nldd-menu')!;
    expect(
      [...menu.querySelectorAll('nldd-menu-item')].map((item) => item.getAttribute('text')),
    ).toEqual(['Start', 'Taken', '**Opdrachten**', 'Team', 'Mensen', 'Inzet', 'Vacatures']);
    expect(menu.querySelector('nldd-menu-item[text="Inzet"]')).toHaveAttribute(
      'accessible-label',
      'Team, Inzet',
    );
  });

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
