import { fireEvent, waitFor } from '@testing-library/react';
import { useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AUTHENTICATED, TEST_PERSON, renderApp } from '@/test/utils';
import { AppShell } from './AppShell';
import { BottomNavigation, MainNavigation, SettingsNavigation } from './MainNavigation';

function stubCount(count: { to_do?: number }) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split('?')[0] ?? '';
      const found = path === '/api/tasks/count';
      return new Response(JSON.stringify(found ? count : { title: 'Niet gevonden' }), {
        status: found ? 200 : 404,
        headers: { 'Content-Type': found ? 'application/json' : 'application/problem+json' },
      });
    }),
  );
}

function GoTo({ to }: { to: string }) {
  const navigate = useNavigate();
  return <button onClick={() => navigate(to)}>{to}</button>;
}

const reader = (functions: string[], relations: string[] = []) => ({
  ...AUTHENTICATED,
  functions,
  relations,
});

const texts = (root: Element, selector: string) =>
  [...root.querySelectorAll(selector)].map((item) => item.getAttribute('text'));

const currentHref = (root: Element) =>
  [...root.querySelectorAll('nldd-tab-bar-item[current]')].map((item) => item.getAttribute('href'));

beforeEach(() => stubCount({}));
afterEach(() => vi.unstubAllGlobals());

describe('the places in the top bar', () => {
  it.each([
    [['beheerder'], [], ['Start', 'Opdrachten', 'Vacatures', 'Mensen', 'Geld']],
    [[], ['assignment_manager'], ['Start', 'Opdrachten', 'Vacatures', 'Mensen', 'Geld']],
    [['planner'], [], ['Start', 'Opdrachten', 'Vacatures', 'Mensen']],
    [['lezer'], [], ['Start', 'Opdrachten', 'Vacatures', 'Geld']],
    [[], ['team_member'], ['Start', 'Opdrachten', 'Vacatures']],
    [['aanvrager'], [], ['Start', 'Aanvragen', 'Vacatures']],
  ])('offers %j %j their own places', (functions, relations, places) => {
    const { container } = renderApp(<MainNavigation />, { auth: reader(functions, relations) });
    expect(texts(container, 'nldd-tab-bar-item')).toEqual(places);
  });

  it('is a navigation bar in a toolbar item, not tabs that switch content', () => {
    const { container } = renderApp(<MainNavigation />);
    const bar = container.querySelector('nldd-tab-bar');
    expect(bar).toHaveAttribute('navigation');
    expect(bar?.parentElement?.tagName.toLowerCase()).toBe('nldd-toolbar-item');
    expect(bar?.parentElement).toHaveAttribute('slot', 'start');
  });

  it('has a link in the menu for every place, for when the bar itself does not fit', () => {
    const { container } = renderApp(<MainNavigation />, { auth: reader(['planner']) });
    const group = container.querySelector('nldd-menu-group[slot="overflow"]');
    expect(group).toHaveAttribute('text', 'Plekken in Grip');
    expect(
      [...(group?.querySelectorAll('nldd-menu-item') ?? [])].map((item) =>
        item.getAttribute('href'),
      ),
    ).toEqual(['/', '/opdrachten', '/vacatures', '/mensen/bord']);
  });

  it.each([
    ['/', '/'],
    ['/taken', '/'],
    ['/wat-is-er-gebeurd', '/'],
    ['/opdrachten/a1/begroting', '/opdrachten'],
    ['/vacatures/v1/tekst', '/vacatures'],
    ['/mensen/p2', '/mensen'],
    ['/mensen/bord', '/mensen'],
    ['/geld/kosten/c1', '/geld'],
    ['/geld/factureren/d1', '/geld'],
  ])('on %s the current place links to %s', (path, href) => {
    const { container } = renderApp(<MainNavigation />, {
      path,
      auth: reader([], ['assignment_manager']),
    });
    expect(currentHref(container)).toEqual([href]);
  });

  it('marks nothing on a page outside every place', () => {
    const { container } = renderApp(<MainNavigation />, { path: '/beveiliging' });
    expect(currentHref(container)).toEqual([]);
  });

  it('draws a new bar only when going between a place and a page outside every place', () => {
    const { container, getByText } = renderApp(
      <>
        <MainNavigation />
        <GoTo to="/vacatures" />
        <GoTo to="/beveiliging" />
      </>,
      { path: '/' },
    );
    const first = container.querySelector('nldd-tab-bar');
    fireEvent.click(getByText('/vacatures'));
    expect(container.querySelector('nldd-tab-bar')).toBe(first);
    fireEvent.click(getByText('/beveiliging'));
    expect(container.querySelector('nldd-tab-bar')).not.toBe(first);
  });

  it('says the number in the text and in the name of the bar', async () => {
    stubCount({ to_do: 10 });
    const { container } = renderApp(<MainNavigation />);
    const bar = () => container.querySelector('nldd-tab-bar');
    await waitFor(() =>
      expect(bar()).toHaveAttribute('accessible-label', 'Plekken in Grip, 10 taken te doen'),
    );
    expect(container.querySelector('nldd-tab-bar-item[href="/"]')).toHaveAttribute(
      'text',
      'Start (10)',
    );
    expect(container.querySelector('nldd-tab-bar-item nldd-badge')).toBeNull();
  });

  it('says one task in the singular', async () => {
    stubCount({ to_do: 1 });
    const { container } = renderApp(<MainNavigation />);
    await waitFor(() =>
      expect(container.querySelector('nldd-tab-bar')).toHaveAttribute(
        'accessible-label',
        'Plekken in Grip, 1 taak te doen',
      ),
    );
  });

  it('counts only what I must do, and says nothing without it', async () => {
    const fetched = vi.fn(
      async () =>
        new Response(JSON.stringify({ open: 3, to_do: 0, overdue: 1 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    );
    vi.stubGlobal('fetch', fetched);
    const { container } = renderApp(<MainNavigation />);
    await waitFor(() => expect(fetched).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(container.querySelector('nldd-tab-bar')).toHaveAttribute(
      'accessible-label',
      'Plekken in Grip',
    );
    expect(container.querySelector('nldd-tab-bar-item[href="/"]')).toHaveAttribute('text', 'Start');
  });
});

describe('the settings in the top bar', () => {
  it('is a second navigation bar, named apart, only for who has settings', () => {
    const { container } = renderApp(<SettingsNavigation />, { auth: reader(['beheerder']) });
    const bar = container.querySelector('nldd-tab-bar');
    expect(bar).toHaveAttribute('navigation');
    expect(bar).toHaveAttribute('accessible-label', 'Instellingen');
    expect(texts(container, 'nldd-tab-bar-item')).toEqual(['Beheer']);
    expect(bar?.parentElement).toHaveAttribute('slot', 'end');
  });

  it('draws nothing for anyone else', () => {
    const { container } = renderApp(<SettingsNavigation />, { auth: reader(['planner']) });
    expect(container.querySelector('nldd-toolbar-item')).toBeNull();
  });
});

describe('the bar at the bottom of a small screen', () => {
  it('ends with Beheer and Ik, each with an icon', () => {
    const { container } = renderApp(<BottomNavigation />, { auth: reader(['beheerder']) });
    expect(texts(container, 'nldd-tab-bar-item')).toEqual([
      'Start',
      'Opdrachten',
      'Vacatures',
      'Mensen',
      'Geld',
      'Beheer',
      'Ik',
    ]);
    for (const item of container.querySelectorAll('nldd-tab-bar-item')) {
      expect(item.getAttribute('icon')).toBeTruthy();
    }
    expect(container.querySelector('nldd-tab-bar-item[text="Ik"]')).toHaveAttribute('href', '/ik');
  });

  it('puts the number on the corner of the icon, as decoration, and in the name of the bar', async () => {
    stubCount({ to_do: 10 });
    const { container } = renderApp(<BottomNavigation />);
    const start = () => container.querySelector('nldd-tab-bar-item[href="/"]');
    await waitFor(() => expect(start()?.querySelector('nldd-badge')).toBeTruthy());
    const badge = start()?.querySelector('nldd-badge');
    expect(badge).toHaveAttribute('number', '10');
    expect(badge).toHaveAttribute('decorative');
    expect(badge?.parentElement).toHaveAttribute('slot', 'icon');
    expect(start()).toHaveAttribute('text', 'Start');
    expect(start()).not.toHaveAttribute('icon');
    expect(container.querySelector('nldd-tab-bar')).toHaveAttribute(
      'accessible-label',
      'Plekken in Grip, 10 taken te doen',
    );
  });

  it('keeps the plain icon on Start without a number', () => {
    const { container } = renderApp(<BottomNavigation />);
    const start = container.querySelector('nldd-tab-bar-item[href="/"]');
    expect(start?.querySelector('nldd-badge')).toBeNull();
    expect(start).toHaveAttribute('icon', 'house');
  });

  it.each(['/ik', '/beveiliging', '/meldingen', `/mensen/${TEST_PERSON.id}`])(
    'marks Ik on %s, which is reached from it',
    (path) => {
      const { container } = renderApp(<BottomNavigation />, {
        path,
        auth: reader(['beheerder']),
      });
      expect(currentHref(container)).toEqual(['/ik']);
    },
  );

  it('keeps someone else under Mensen', () => {
    const { container } = renderApp(<BottomNavigation />, {
      path: '/mensen/p-2',
      auth: reader(['beheerder']),
    });
    expect(currentHref(container)).toEqual(['/mensen']);
  });
});

describe('the shell', () => {
  it('has the top bar above the page and the bottom bar after it', () => {
    const { container } = renderApp(<AppShell />, { auth: reader(['beheerder']) });
    const panes = [...container.querySelectorAll('nldd-bar-split-view > nldd-split-view-pane')];
    expect(panes.map((pane) => pane.getAttribute('slot'))).toEqual([
      'toolbar',
      'main',
      'toolbar-sm',
    ]);
    expect(panes[0]).toHaveAttribute('above', 'md');
    expect(panes[2]).toHaveAttribute('only', 'sm');
    expect(panes[2]?.querySelector('nldd-toolbar')).toHaveAttribute('size', 'lg');
  });

  it('has no menu bar and no menu button', () => {
    const { container } = renderApp(<AppShell />, { auth: reader(['beheerder']) });
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
    expect(container.querySelector('nldd-button[start-icon="list"]')).toBeNull();
  });

  it('has Ik only at the bottom, and the account only at the top', () => {
    const { container } = renderApp(<AppShell />);
    const [top, , bottom] = [
      ...container.querySelectorAll('nldd-bar-split-view > nldd-split-view-pane'),
    ];
    expect(top?.querySelector('nldd-tab-bar-item[text="Ik"]')).toBeNull();
    expect(bottom?.querySelector('nldd-tab-bar-item[text="Ik"]')).toBeTruthy();
    expect(top?.querySelector('[data-account-menu]')).toBeTruthy();
    expect(bottom?.querySelector('[data-account-menu]')).toBeNull();
  });

  it('keeps a place for the search field in the centre of the top bar, with a way in the menu', () => {
    const { container } = renderApp(<AppShell />);
    const item = container.querySelector('nldd-toolbar-item[slot="center"]');
    expect(item).toHaveAttribute('min-width', '240px');
    expect(item?.querySelector('nldd-menu-item[slot="overflow"]')).toHaveAttribute(
      'href',
      '/zoeken',
    );
  });
});
