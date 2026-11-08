import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from './AppRoutes';
import { PATHS } from './paths';
import {
  APP_ROUTES,
  currentRoute,
  isCurrentRoute,
  landingPath,
  navLabel,
  routesFor,
} from './routes';
import { AUTHENTICATED, renderApp } from './test/utils';

const PLANNER = { ...AUTHENTICATED, functions: ['planner'] };
const TOP_BAR = 'nldd-split-view-pane[slot="toolbar"]';

describe('route table', () => {
  it('lists the places in the order of the bar, with the settings last', () => {
    expect(APP_ROUTES.map(navLabel)).toEqual([
      'Start',
      'Opdrachten',
      'Aanvragen',
      'Vacatures',
      'Mensen',
      'Geld',
      'Beheer',
    ]);
    expect(APP_ROUTES.filter((route) => route.area === 'settings').map((r) => r.title)).toEqual([
      'Beheer',
    ]);
  });

  it('offers each reader only the places that can hold something for them', () => {
    const labels = (functions: string[], relations: string[] = []) =>
      routesFor({ functions, relations }).map(navLabel);
    // The role of client is for who holds it; a beheerder reaches it from Beheer.
    expect(labels(['beheerder'])).toEqual([
      'Start',
      'Opdrachten',
      'Vacatures',
      'Mensen',
      'Geld',
      'Beheer',
    ]);
    // Owner or manager of assignments: the work and its money, no settings, no client role.
    expect(labels([], ['assignment_manager'])).toEqual([
      'Start',
      'Opdrachten',
      'Vacatures',
      'Mensen',
      'Geld',
    ]);
    expect(labels(['planner'])).toEqual(['Start', 'Opdrachten', 'Vacatures', 'Mensen']);
    expect(labels([], ['line_manager'])).toEqual(['Start', 'Vacatures', 'Mensen']);
    expect(labels(['lezer'])).toEqual(['Start', 'Opdrachten', 'Vacatures', 'Geld']);
    expect(labels([], ['team_member'])).toEqual(['Start', 'Opdrachten', 'Vacatures']);
    expect(labels(['aanvrager'])).toEqual(['Start', 'Aanvragen', 'Vacatures']);
    expect(labels(['tekenbevoegde'])).toEqual(['Start', 'Aanvragen', 'Vacatures']);
    expect(labels([])).toEqual(['Start', 'Vacatures']);
  });

  it('opens Mensen on the board for a planner and on the list for everyone else', () => {
    const people = APP_ROUTES.find((route) => route.title === 'Mensen')!;
    const start = APP_ROUTES[0]!;
    expect(landingPath(people, { functions: ['planner'], relations: [] })).toBe('/mensen/bord');
    expect(landingPath(people, { functions: [], relations: ['line_manager'] })).toBe('/mensen');
    expect(landingPath(people, { functions: ['beheerder'], relations: [] })).toBe('/mensen');
    expect(landingPath(start, { functions: [], relations: [] })).toBe('/');
  });

  it('knows which place a deeper page belongs to', () => {
    const section = (path: string) => currentRoute(path)?.title;
    expect(section('/')).toBe('Start');
    expect(section('/opdrachten/a1/offerte')).toBe('Opdrachten');
    expect(section('/opdrachten/a1/geschiedenis')).toBe('Opdrachten');
    expect(section('/geld/kosten/c1')).toBe('Geld');
    expect(section('/geld/factureren/d1')).toBe('Geld');
    expect(section('/mensen/p1')).toBe('Mensen');
    expect(section('/mensen/bord')).toBe('Mensen');
    expect(section('/vacatures/opengesteld')).toBe('Vacatures');
    expect(section('/aanvragen/offerte/q1')).toBe('Aanvragen');
    // Work that reaches you on the start page.
    expect(section('/taken')).toBe('Start');
    expect(section('/goedkeuren')).toBe('Start');
    expect(section('/goedkeuren/q1')).toBe('Start');
    expect(section('/wat-is-er-gebeurd')).toBe('Start');
    // Reached from Beheer, whatever the address says.
    expect(section('/beheer/offertes')).toBe('Beheer');
    expect(section('/beheer/activiteit')).toBe('Beheer');
    expect(section('/vacatures/beheer')).toBe('Beheer');
    expect(section('/bestaat-niet')).toBeUndefined();
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
    expect(isCurrentRoute('/mensen', '/mensenlijst')).toBe(false);
  });
});

describe('routes', () => {
  /** The heading of each place, by address. */
  const HEADINGS: Record<string, string> = {
    '/': 'Start',
    '/opdrachten': 'Opdrachten',
    '/aanvragen': 'Aanvragen',
    '/vacatures': 'Vacatures',
    '/mensen': 'Mensen',
    '/geld': 'Geld',
    '/beheer': 'Beheer',
  };
  /** Someone who is offered every place, the role of client included. */
  const ALL = { ...AUTHENTICATED, functions: ['beheerder', 'aanvrager'] };
  const PLACES = APP_ROUTES.map((route) => [route.path, navLabel(route)] as const);

  it.each(PLACES)('renders %s with exactly one h1 and marks %s current', async (path, label) => {
    const { container } = renderApp(<AppRoutes />, { path, auth: ALL });

    // Most pages are a file of their own: wait for it.
    const headings = await screen.findAllByRole('heading', { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent(HEADINGS[path]!);
    expect(document.title).toBe(`${HEADINGS[path]} · Testinstantie · grip`);

    const current = container.querySelectorAll(`${TOP_BAR} nldd-tab-bar-item[current]`);
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute('text', label);
  });

  it.each([
    ['/mensen/bord', 'Bord'],
    ['/mensen/bezetting', 'Bezetting'],
    ['/mensen/declarabiliteit', 'Declarabiliteit'],
    ['/geld/opdrachten', 'Lopende opdrachten'],
    ['/geld/omzet', 'Omzet'],
    ['/geld/investeerruimte', 'Investeerruimte'],
    ['/geld/potentieel', 'Potentieel'],
    ['/geld/kosten', 'Kosten'],
    ['/geld/factureren', 'Factureren'],
    ['/geld/jaarverantwoording', 'Jaarverantwoording'],
    ['/taken', 'Taken'],
    ['/zoeken', 'Zoeken'],
    ['/ik', 'Ik'],
  ])('gives %s the page %s', async (path, heading) => {
    renderApp(<AppRoutes />, { path, auth: ALL });
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(heading);
  });

  it.each([
    '/inzet',
    '/kosten',
    '/factureren',
    '/team',
    '/team/p1',
    '/tarieven',
    '/rapportage',
    '/rapportage/omzet',
    '/rapportage/opdrachten/a1',
    '/opdrachten/a1/financieel',
    '/opdrachten/a1/bemensing',
    '/opdrachten/a1/maandafsluiting',
    '/vacatures/v1/procedure',
  ])('has no page at the old address %s', (path) => {
    renderApp(<AppRoutes />, { path, auth: ALL });
    expect(
      screen.getByRole('heading', { level: 1, name: 'Pagina niet gevonden' }),
    ).toBeInTheDocument();
  });

  it('keeps the place on a deeper page', () => {
    const { container } = renderApp(<AppRoutes />, { path: '/mensen/p1', auth: ALL });
    expect(container.querySelector(`${TOP_BAR} nldd-tab-bar-item[current]`)).toHaveAttribute(
      'text',
      'Mensen',
    );
  });

  it('sends a planner to the board', () => {
    const { container } = renderApp(<AppRoutes />, { path: '/opdrachten', auth: PLANNER });
    expect(container.querySelector(`${TOP_BAR} nldd-tab-bar-item[text="Mensen"]`)).toHaveAttribute(
      'href',
      '/mensen/bord',
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
      path: '/mensen',
      auth: { status: 'no-access' },
      logout,
    });

    expect(screen.getByRole('heading', { level: 1, name: 'Geen toegang' })).toBeInTheDocument();
    container.querySelector('nldd-button')?.dispatchEvent(new Event('click'));
    expect(logout).toHaveBeenCalledOnce();
  });

  it('sends an authenticated person away from the login page', () => {
    renderApp(<AppRoutes />, { path: PATHS.login });
    expect(screen.getByRole('heading', { level: 1, name: 'Start' })).toBeInTheDocument();
  });
});
