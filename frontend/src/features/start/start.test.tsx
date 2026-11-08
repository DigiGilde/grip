import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { allText, mockApi, plain } from '@/features/assignments/testing';
import { renderApp } from '@/test/utils';
import type { StartData } from './api';
import { StartPage } from './StartPage';

afterEach(() => vi.unstubAllGlobals());

function narrowWindow(narrow: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation(() => ({
      matches: narrow,
      addEventListener: () => {},
      removeEventListener: () => {},
    })),
  );
}

const group = (overrides: Partial<StartData['to_do']['groups'][number]> = {}) => ({
  case_kind: 'assignment' as const,
  case_id: 'a1',
  case_label: 'Opdracht Alfa 2026',
  task_id: 't1',
  headline: 'Sluit maart 2026 af',
  href: '/opdrachten/a1/afsluiten',
  overdue: true,
  due_on: '2026-04-07',
  more_text: 'daarna nog 7 maanden',
  ...overrides,
});

const NOTHING: StartData = { to_do: { groups: [], total: 0 } };

const UPDATES = {
  items: [
    {
      id: 'u1',
      seq: 3,
      kind: 'x',
      when: '2026-11-04T08:00:00Z',
      when_text: 'vanochtend',
      day: 'Vandaag',
      parts: [{ text: 'Opdracht Alfa 2026', href: '/opdrachten/a1' }, { text: ' is gestart' }],
      text: 'Opdracht Alfa 2026 is gestart',
      count: 1,
      new: false,
    },
  ],
  new_count: 0,
  next: null,
};

function renderStart(start: StartData, updates: unknown = { items: [], new_count: 0, next: null }) {
  const fetchMock = mockApi({
    '/api/start': start,
    '/api/updates': updates,
    '/api/updates/seen': {},
  });
  const view = renderApp(<StartPage />);
  return { ...view, fetchMock };
}

const titles = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-title[text]')].map((title) => title.getAttribute('text'));
const links = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-list-item[href]')].map((item) => item.getAttribute('href'));
const rowTexts = (container: HTMLElement, label?: string) =>
  [
    ...container.querySelectorAll(
      `${label ? `nldd-list[accessible-label="${label}"] ` : ''}nldd-text-cell`,
    ),
  ].map((cell) => cell.getAttribute('text'));
const linksIn = (container: HTMLElement, label: string) =>
  [
    ...container.querySelectorAll(`nldd-list[accessible-label="${label}"] nldd-list-item[href]`),
  ].map((item) => item.getAttribute('href'));

describe('Start: the to-do block', () => {
  it('shows a row per case with the case under it, a label when late, and the way to all tasks', async () => {
    const { container } = renderStart({
      to_do: {
        groups: [
          group(),
          group({
            task_id: 't2',
            case_id: 'v1',
            case_kind: 'vacancy',
            case_label: 'Vacature Ontwerper',
            headline: 'Schrijf de vacaturetekst',
            href: '/vacatures/v1/tekst',
            overdue: false,
            due_on: null,
            more_text: 'daarna nog 2 taken',
          }),
        ],
        total: 10,
      },
    });
    await waitFor(() => expect(titles(container)).toContain('Te doen'));
    const items = [
      ...container.querySelectorAll('nldd-list[accessible-label="Te doen"] nldd-list-item'),
    ];
    expect(items).toHaveLength(3);
    const first = items[0]!.querySelector('nldd-text-cell');
    expect(first?.getAttribute('text')).toBe('Sluit maart 2026 af');
    expect(first?.getAttribute('supporting-text')).toBe('Opdracht Alfa 2026, daarna nog 7 maanden');
    expect(items[0]!.getAttribute('href')).toBe('/opdrachten/a1/afsluiten');
    expect(items[0]!.querySelector('nldd-badge')?.getAttribute('text')).toBe('Te laat');
    expect(items[1]!.querySelector('nldd-badge')).toBeNull();
    expect(items[2]!.getAttribute('href')).toBe('/taken');
    expect(items[2]!.querySelector('nldd-text-cell')?.getAttribute('text')).toBe('Alle taken (10)');
  });

  it('shows a row without a link when the server has no address for it', async () => {
    const { container } = renderStart({
      to_do: { groups: [group({ href: null })], total: 1 },
    });
    await waitFor(() => expect(titles(container)).toContain('Te doen'));
    const row = container.querySelector('nldd-list[accessible-label="Te doen"] nldd-list-item');
    expect(row?.hasAttribute('href')).toBe(false);
    expect(row?.querySelector('nldd-icon-cell')).toBeNull();
    expect(row?.querySelector('nldd-text-cell')?.getAttribute('text')).toBe('Sluit maart 2026 af');
  });

  it('says in one line that there is nothing to do and keeps the link to all tasks', async () => {
    const { container } = renderStart(NOTHING);
    await waitFor(() => expect(titles(container)).toContain('Te doen'));
    expect(screen.getAllByText('Niets te doen')).toHaveLength(1);
    expect(rowTexts(container)).toEqual(['Alle taken']);
    expect(links(container)).toEqual(['/taken']);
  });

  it('has no filters and asks neither for a year nor for the old overview', async () => {
    const { container, fetchMock } = renderStart({
      to_do: { groups: [group()], total: 1 },
    });
    await waitFor(() => expect(titles(container)).toContain('Te doen'));
    expect(container.querySelector('nldd-dropdown, select, nldd-segmented-control')).toBeNull();
    const calls = (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(calls.some((url) => url.startsWith('/api/overview'))).toBe(false);
    expect(calls.some((url) => url.startsWith('/api/tasks/mine'))).toBe(false);
  });
});

describe('Start: what concerns the reader', () => {
  it('shows what a team member works on, the warning under its row, and the way to the own data', async () => {
    const { container } = renderStart({
      ...NOTHING,
      my_work: {
        person_id: 'p9',
        rows: [
          {
            assignment_id: 'a1',
            name: 'Opdracht Alfa 2026',
            line: 'Developer, 100%, tot 31 dec 2026',
            warning: 'Geen inzet vanaf januari 2027',
          },
          {
            assignment_id: 'a2',
            name: 'Opdracht Beta 2026',
            line: 'Developer, 20%',
            warning: null,
          },
        ],
        total: 2,
      },
    });
    await waitFor(() => expect(titles(container)).toContain('Je werkt aan'));
    const list = container.querySelector('nldd-list[accessible-label="Je werkt aan"]')!;
    const texts = [...list.querySelectorAll('nldd-text-cell')].map((cell) =>
      cell.getAttribute('text'),
    );
    expect(texts).toEqual([
      'Opdracht Alfa 2026',
      'Geen inzet vanaf januari 2027',
      'Opdracht Beta 2026',
      'Mijn gegevens',
    ]);
    const hrefs = [...list.querySelectorAll('nldd-list-item')].map((item) =>
      item.getAttribute('href'),
    );
    expect(hrefs).toEqual(['/opdrachten/a1', null, '/opdrachten/a2', '/mensen/p9']);
  });

  it('cuts a block at its rows and says how many there are', async () => {
    const { container } = renderStart({
      ...NOTHING,
      my_assignments: {
        rows: [
          { assignment_id: 'a1', name: 'Opdracht Alfa 2026', line: 'Uitvoeren', verdict: null },
        ],
        total: 50,
      },
    });
    await waitFor(() => expect(titles(container)).toContain('Mijn opdrachten'));
    expect(rowTexts(container)).toContain('Alle 50');
    expect(links(container)).toContain('/opdrachten');
  });

  it('puts the overrun first and labels room and overrun, nothing while there is no verdict', async () => {
    const { container } = renderStart({
      ...NOTHING,
      my_assignments: {
        rows: [
          { assignment_id: 'a1', name: 'Opdracht Alfa 2026', line: 'Uitvoeren', verdict: 'room' },
          {
            assignment_id: 'a2',
            name: 'Opdracht Beta 2026',
            line: 'Uitvoeren',
            verdict: 'overrun',
          },
          { assignment_id: 'a3', name: 'Opdracht Epsilon 2027', line: 'Aanbieden', verdict: null },
        ],
        total: 3,
      },
    });
    await waitFor(() => expect(titles(container)).toContain('Mijn opdrachten'));
    const list = container.querySelector('nldd-list[accessible-label="Mijn opdrachten"]')!;
    const rows = [...list.querySelectorAll('nldd-list-item')].map((item) => [
      item.querySelector('nldd-text-cell')?.getAttribute('text'),
      item.querySelector('nldd-badge')?.getAttribute('text') ?? null,
    ]);
    expect(rows).toEqual([
      ['Opdracht Beta 2026', 'Overschrijding'],
      ['Opdracht Alfa 2026', 'Ruimte'],
      ['Opdracht Epsilon 2027', null],
    ]);
  });

  it('shows planning as rows to the board, and leaves out a row that is 0', async () => {
    const both = renderStart({
      ...NOTHING,
      planning: { open_roles: 5, open_fte: '4.1', idle_people: 11, idle_from: '2027-01-01' },
    });
    await waitFor(() => expect(titles(both.container)).toContain('Planning'));
    expect(rowTexts(both.container, 'Planning')).toEqual([
      '5 open rollen, 4,1 FTE',
      '11 mensen zonder inzet vanaf januari 2027',
    ]);
    expect(linksIn(both.container, 'Planning')).toEqual(['/mensen/bord', '/mensen/bord']);
    both.unmount();

    const onlyRoles = renderStart({
      ...NOTHING,
      planning: { open_roles: 1, open_fte: '0.8', idle_people: 0, idle_from: null },
    });
    await waitFor(() => expect(titles(onlyRoles.container)).toContain('Planning'));
    expect(rowTexts(onlyRoles.container, 'Planning')).toEqual(['1 open rol, 0,8 FTE']);
    onlyRoles.unmount();

    const onlyIdle = renderStart({
      ...NOTHING,
      planning: { open_roles: 0, open_fte: '0', idle_people: 1, idle_from: '2027-01-01' },
    });
    await waitFor(() => expect(titles(onlyIdle.container)).toContain('Planning'));
    expect(rowTexts(onlyIdle.container, 'Planning')).toEqual([
      '1 mens zonder inzet vanaf januari 2027',
    ]);
  });

  it('has no planning block when both counts are 0', async () => {
    const { container } = renderStart({
      ...NOTHING,
      planning: { open_roles: 0, open_fte: '0', idle_people: 0, idle_from: null },
    });
    await waitFor(() => expect(titles(container)).toContain('Te doen'));
    expect(titles(container)).not.toContain('Planning');
  });

  it('shows inzet now and free from per person, and only what is known', async () => {
    const { container } = renderStart({
      ...NOTHING,
      my_people: {
        rows: [
          { person_id: 'p1', name: 'Daan Developer', now_pct: '100', free_from: '2027-01-01' },
          { person_id: 'p2', name: 'Anna Analist', now_pct: '80', free_from: null },
          { person_id: 'p3', name: 'Olaf Ontwerper', now_pct: null, free_from: null },
        ],
        total: 3,
      },
    });
    await waitFor(() => expect(titles(container)).toContain('Mijn mensen'));
    const list = container.querySelector('nldd-list[accessible-label="Mijn mensen"]')!;
    const cells = [...list.querySelectorAll('nldd-text-cell')].map((cell) => [
      cell.getAttribute('text'),
      cell.getAttribute('supporting-text'),
    ]);
    expect(cells).toEqual([
      ['Daan Developer', 'Inzet nu 100%, vrij vanaf januari 2027'],
      ['Anna Analist', 'Inzet nu 80%'],
      ['Olaf Ontwerper', null],
    ]);
    expect(linksIn(container, 'Mijn mensen')).toEqual(['/mensen/p1', '/mensen/p2', '/mensen/p3']);
  });

  it('says the potential is over the whole run, and the other figures are of the year', async () => {
    const { container } = renderStart({
      ...NOTHING,
      figures: {
        year: 2026,
        expected_cents: 103230000,
        budgeted_cents: 115680000,
        room_cents: -40040000,
        shortfall: true,
        potential_cents: 43440000,
        quotes_waiting: 1,
      },
    });
    await waitFor(() => expect(titles(container)).toContain('Hoe staan we ervoor'));
    const text = plain(allText(container));
    expect(text).toContain('Verwacht totaal 2026');
    expect(text).toContain('Van € 1.156.800 begroot');
    expect(text).toContain('€ 1.032.300');
    expect(text).toContain('Investeerruimte 2026');
    expect(text).toContain('€ 400.400 tekort');
    expect(text).toContain('1 offerte wacht op akkoord, hele looptijd');
    expect(text).toContain('€ 434.400');
    expect(linksIn(container, 'Hoe staan we ervoor')).toEqual([
      '/geld/omzet',
      '/geld/investeerruimte',
      '/geld/potentieel',
    ]);
  });

  it('shows no room, not even 0, when the server leaves it out', async () => {
    const { container } = renderStart({
      ...NOTHING,
      figures: {
        year: 2026,
        expected_cents: 5000000,
        budgeted_cents: 6000000,
        potential_cents: 1000000,
        quotes_waiting: 2,
      },
    });
    await waitFor(() => expect(titles(container)).toContain('Hoe staan we ervoor'));
    const text = plain(allText(container));
    expect(text).not.toContain('Investeerruimte');
    expect(text).not.toContain('tekort');
    expect(text).toContain('2 offertes wachten op akkoord, hele looptijd');
  });

  it('shows a room that is there as an amount, without "tekort"', async () => {
    const { container } = renderStart({
      ...NOTHING,
      figures: {
        year: 2026,
        expected_cents: 5000000,
        budgeted_cents: 6000000,
        room_cents: 250000,
        shortfall: false,
        potential_cents: 0,
        quotes_waiting: 0,
      },
    });
    await waitFor(() => expect(titles(container)).toContain('Hoe staan we ervoor'));
    const text = plain(allText(container));
    expect(text).toContain('Investeerruimte 2026');
    expect(text).toContain('€ 2.500');
    expect(text).not.toContain('tekort');
    expect(text).not.toContain('Potentieel');
  });

  it('shows the requests of a client, each to its own page', async () => {
    const { container } = renderStart({
      ...NOTHING,
      my_requests: {
        rows: [{ assignment_id: 'a7', name: 'Opdracht Zeta', line: 'Nog geen offerte' }],
        total: 1,
      },
    });
    await waitFor(() => expect(titles(container)).toContain('Mijn aanvragen'));
    expect(links(container)).toContain('/aanvragen/opdracht/a7');
    expect(plain(allText(container))).toContain('Nog geen offerte');
  });

  it('shows connections for the administrator who has a problem', async () => {
    const { container } = renderStart({ ...NOTHING, connections: { problems: 2 } });
    await waitFor(() => expect(titles(container)).toContain('Verbindingen'));
    expect(links(container)).toContain('/beheer/koppelingen');
  });

  it('shows only the to-do block and what is new to a reader with nothing else, and no 0%', async () => {
    const { container } = renderStart(NOTHING, UPDATES);
    await waitFor(() => expect(titles(container)).toContain('Nieuw'));
    expect(titles(container)).toEqual(['Te doen', 'Nieuw']);
    expect(plain(allText(container))).not.toContain('0%');
  });

  it('stands in the order of the page: to do, what concerns the reader, new', async () => {
    const { container } = renderStart(
      {
        to_do: { groups: [group()], total: 1 },
        my_work: { person_id: 'p9', rows: [], total: 0 },
        planning: { open_roles: 1, open_fte: '1', idle_people: 0, idle_from: null },
        my_assignments: { rows: [], total: 0 },
        my_people: { rows: [], total: 0 },
        figures: {
          year: 2026,
          expected_cents: 1,
          budgeted_cents: 1,
          potential_cents: 0,
          quotes_waiting: 0,
        },
        my_requests: { rows: [], total: 0 },
        connections: { problems: 1 },
      },
      UPDATES,
    );
    await waitFor(() => expect(titles(container)).toContain('Nieuw'));
    expect(titles(container)).toEqual([
      'Te doen',
      'Je werkt aan',
      'Planning',
      'Mijn opdrachten',
      'Mijn mensen',
      'Hoe staan we ervoor',
      'Mijn aanvragen',
      'Verbindingen',
      'Nieuw',
    ]);
  });
});

describe('Start: what is new', () => {
  it('shows at most three rows and the link to everything', async () => {
    const { container, fetchMock } = renderStart(NOTHING, UPDATES);
    await waitFor(() => expect(titles(container)).toContain('Nieuw'));
    const calls = (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(calls).toContain('/api/updates?limiet=3');
    const list = container.querySelector('nldd-list[accessible-label="Wat er gebeurde"]')!;
    const rows = [...list.querySelectorAll('nldd-list-item')];
    expect(rows.map((row) => row.getAttribute('href'))).toEqual([
      '/opdrachten/a1',
      '/wat-is-er-gebeurd',
    ]);
    expect(rows[0]!.querySelector('nldd-text-cell')?.getAttribute('text')).toBe(
      'Opdracht Alfa 2026 is gestart',
    );
    expect(rows[0]!.querySelector('nldd-text-cell')?.getAttribute('supporting-text')).toBe(
      'vanochtend',
    );
    expect(rows[1]!.querySelector('nldd-text-cell')?.getAttribute('text')).toBe(
      'Alles wat er gebeurd is',
    );
  });

  it('leaves the block out when nothing happened', async () => {
    const { container } = renderStart(NOTHING);
    await waitFor(() => expect(titles(container)).toContain('Te doen'));
    await waitFor(() => expect(screen.queryByText('Laden')).toBeNull());
    expect(titles(container)).not.toContain('Nieuw');
  });
});

describe('Start: the search field', () => {
  it('stands above the title on a narrow screen', async () => {
    narrowWindow(true);
    const { container } = renderStart(NOTHING);
    await waitFor(() => expect(titles(container)).toContain('Te doen'));
    const field = container.querySelector('nldd-search-field');
    expect(field).not.toBeNull();
    const heading = container.querySelector('#page-heading');
    expect(heading).not.toBeNull();
    expect(
      field!.compareDocumentPosition(heading!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('is left to the bar on a wide screen', async () => {
    narrowWindow(false);
    const { container } = renderStart(NOTHING);
    await waitFor(() => expect(titles(container)).toContain('Te doen'));
    expect(container.querySelector('nldd-search-field')).toBeNull();
  });
});
