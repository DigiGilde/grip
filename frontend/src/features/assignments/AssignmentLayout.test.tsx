import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AssignmentHistoryTab } from '@/features/history/History';
import { COURSE_KEYS } from '@/features/tasks/course';
import { renderApp } from '@/test/utils';
import type { AssignmentPermissions } from './api';
import { AssignmentLayout } from './AssignmentLayout';
import { StaffingTab } from './tabs/StaffingTab';
import { FIGURES, PERMISSIONS, allText, assignment, finance, mockApi } from './testing';

afterEach(() => vi.unstubAllGlobals());

const MONTHS = [
  '2026-01-01',
  '2026-02-01',
  '2026-03-01',
  '2026-04-01',
  '2026-05-01',
  '2026-06-01',
  '2026-07-01',
  '2026-08-01',
  '2026-09-01',
  '2026-10-01',
  '2026-11-01',
  '2026-12-01',
];

const STAFFING = {
  assignment_id: 'a1',
  months: MONTHS,
  current_month: '2026-04-01',
  closed_months: ['2026-01-01'],
  tentative: false,
  role_count: 1,
  staffed_count: 0,
  open_fte: '0.30',
  open_from: '2026-10-01',
  overbooked_count: 1,
  overbooked: [
    { person_id: 'p1', person_name: 'Voorbeeld Een', month: '2026-10-01', pct: '140.0' },
  ],
  roles: [
    {
      budget_line_id: 'l1',
      description: 'Productmanager',
      role: 'Productmanager',
      fte: '0.800',
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      fully_staffed: false,
      can_fill: true,
      names: ['Voorbeeld Een', 'Voorbeeld Twee'],
      months: MONTHS.map((month, index) => ({
        month,
        asked_pct: '80',
        filled_pct: index < 9 ? '80' : '50',
        open_pct: index < 9 ? '0' : '30',
        over: false,
        closed: index === 0,
      })),
      gaps: [{ start: '2026-10-01', end: '2026-12-01', open_fte: '0.30' }],
      bars: [
        {
          allocation_id: 'x1',
          person_id: 'p1',
          person_name: 'Voorbeeld Een',
          budget_line_id: 'l1',
          tentative: false,
          verbally_agreed: false,
          start_date: '2026-01-01',
          end_date: '2026-12-31',
          fte_pct: '50.00',
          closed_months: ['2026-01-01'],
          can_edit: true,
          category_mismatch: true,
          starts_on: null,
          before_start: false,
          outside_role_period: false,
        },
        {
          allocation_id: 'x2',
          person_id: 'p2',
          person_name: 'Voorbeeld Twee',
          budget_line_id: 'l1',
          tentative: false,
          verbally_agreed: false,
          start_date: '2026-01-01',
          end_date: '2026-09-30',
          fte_pct: '30.00',
          closed_months: [],
          can_edit: true,
          category_mismatch: false,
          starts_on: '2026-12-01',
          before_start: true,
          outside_role_period: false,
        },
      ],
    },
  ],
};

const NAMES_ONLY = {
  assignment_id: 'a1',
  months: MONTHS,
  current_month: '2026-04-01',
  tentative: false,
  roles: [
    { budget_line_id: 'l1', description: 'Productmanager', bars: [], names: ['Voorbeeld Een'] },
  ],
};

function renderShell(
  permissions: AssignmentPermissions,
  path = '/opdrachten/a1',
  overrides = {},
  staffing: unknown = STAFFING,
  money: unknown = finance(),
  extra: Record<string, unknown> = {},
) {
  mockApi({
    ...extra,
    '/api/assignments/a1/financial': money,
    '/api/assignments/a1/staffing': staffing,
    '/api/allocations/options': { people: [], lines: [] },
    '/api/assignments/a1': assignment({ permissions, ...overrides }),
    '/api/vacancies': [],
  });
  return renderApp(
    <Routes>
      <Route path="/opdrachten/:assignmentId" element={<AssignmentLayout />}>
        <Route index element={<p>overzicht</p>} />
        <Route path="bemensing" element={<StaffingTab />} />
        <Route path="geschiedenis" element={<AssignmentHistoryTab />} />
      </Route>
    </Routes>,
    { path },
  );
}

async function tabs(container: HTMLElement) {
  await waitFor(() => expect(container.querySelector('nldd-menu-bar')).not.toBeNull());
  return [...container.querySelectorAll('nldd-menu-bar-item')].map((item) =>
    item.getAttribute('text'),
  );
}

describe('AssignmentLayout', () => {
  it('shows an owner every tab, each with its own address', async () => {
    const { container } = renderShell(PERMISSIONS.owner);
    expect(await tabs(container)).toEqual([
      'Overzicht',
      'Taken',
      'Financieel',
      'Bemensing',
      'Begroting',
      'Offerte',
      'Afsluiten en factureren',
      'Geschiedenis',
    ]);
    const hrefs = [...container.querySelectorAll('nldd-menu-bar-item')].map((item) =>
      item.getAttribute('href'),
    );
    expect(hrefs).toEqual([
      '/opdrachten/a1',
      '/opdrachten/a1/taken',
      '/opdrachten/a1/financieel',
      '/opdrachten/a1/bemensing',
      '/opdrachten/a1/begroting',
      '/opdrachten/a1/offerte',
      '/opdrachten/a1/maandafsluiting',
      '/opdrachten/a1/geschiedenis',
    ]);
    // A navigation landmark with a name; the menu bar is one by itself.
    expect(container.querySelector('nldd-menu-bar')).toHaveAttribute('accessible-label');
    // Never the segmented control: a filled current tab reads as a button.
    expect(container.querySelector('nldd-tab-bar')).toBeNull();
  });

  it('shows a planner no money tab', async () => {
    const { container } = renderShell(PERMISSIONS.planner);
    expect(await tabs(container)).toEqual([
      'Overzicht',
      'Taken',
      'Bemensing',
      'Afsluiten en factureren',
      'Geschiedenis',
    ]);
  });

  it('shows a team member the overview and the team', async () => {
    const { container } = renderShell(PERMISSIONS.member);
    expect(await tabs(container)).toEqual(['Overzicht', 'Taken', 'Bemensing', 'Geschiedenis']);
  });

  it('shows a lezer the money tabs and no team', async () => {
    const { container } = renderShell(PERMISSIONS.lezer);
    expect(await tabs(container)).toEqual([
      'Overzicht',
      'Taken',
      'Financieel',
      'Begroting',
      'Offerte',
      'Afsluiten en factureren',
      'Geschiedenis',
    ]);
  });

  it('marks the tab of the current address', async () => {
    const { container } = renderShell(PERMISSIONS.owner, '/opdrachten/a1/bemensing');
    await tabs(container);
    const current = container.querySelectorAll('nldd-menu-bar-item[current]');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute('text', 'Bemensing');
  });

  it('shows key figures only to who may see money', async () => {
    const owner = renderShell(PERMISSIONS.owner);
    await waitFor(() =>
      expect(owner.container.querySelector('dl[aria-label^="Kerncijfers"]')).not.toBeNull(),
    );
    expect(allText(owner.container)).toContain('187.800');
    owner.unmount();

    const planner = renderShell(PERMISSIONS.planner);
    await tabs(planner.container);
    expect(planner.container.querySelector('dl[aria-label^="Kerncijfers"]')).toBeNull();
    expect(allText(planner.container)).not.toContain('€');
  });

  it('says under the headline facts that they miss what another organisation keeps', async () => {
    const { container } = renderShell(
      PERMISSIONS.owner,
      '/opdrachten/a1',
      {},
      STAFFING,
      finance({ incomplete_by: ['Voorbeeldgilde'] }),
    );
    await tabs(container);
    await waitFor(() =>
      expect(container.querySelector('dl[aria-label^="Kerncijfers"] + p')).toHaveTextContent(
        'Onvolledig: niet alles is op te halen bij Voorbeeldgilde',
      ),
    );
  });

  it('draws no row of zeros for an assignment with nothing budgeted, done or planned', async () => {
    // What the server answers for an assignment that was just made: zeros, not absence.
    const empty = {
      ...FIGURES,
      budgeted_cents: 0,
      realised_cents: 0,
      planned_cents: 0,
      costs_realised_cents: 0,
      costs_forecast_cents: 0,
      costs_cents: 0,
      expected_total_cents: 0,
      variance_cents: 0,
      variance_pct: '0',
      realised_total_cents: 0,
      realised_pct: '0',
    };
    const { container } = renderShell(
      PERMISSIONS.owner,
      '/opdrachten/a1',
      {},
      STAFFING,
      finance({ totals: empty }),
    );
    await tabs(container);
    await waitFor(() => expect(allText(container)).toContain('Overzicht'));
    expect(container.querySelector('dl[aria-label^="Kerncijfers"]')).toBeNull();
    expect(allText(container)).not.toContain('Geen ruimte');
    expect(allText(container)).not.toContain('€ 0');
  });

  it('asks for the whole period, and does not call a budget without inzet all room', async () => {
    // An assignment that lies entirely in a later year: budgeted, nothing planned yet.
    const later = {
      ...FIGURES,
      realised_total_cents: 0,
      expected_total_cents: 0,
      variance_cents: 43440000,
      variance_pct: '100',
      budgeted_cents: 43440000,
    };
    const { container } = renderShell(
      PERMISSIONS.owner,
      '/opdrachten/a1',
      { start_date: '2027-01-01', end_date: '2027-12-31' },
      STAFFING,
      finance({ totals: later }),
    );
    await waitFor(() =>
      expect(container.querySelector('dl[aria-label^="Kerncijfers"]')).not.toBeNull(),
    );
    const text = allText(container);
    expect(text).toContain('434.400');
    expect(text).toContain('Nog geen inzet gepland');
    expect(text).not.toContain('Ruimte');
    expect(text).not.toContain('100');
    const calls = (vi.mocked(fetch).mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(calls).toContain('/api/assignments/a1/financial?year=all');
  });

  it('says how the reader sees the assignment, with or without a relation of their own', async () => {
    const owner = renderShell(PERMISSIONS.owner, '/opdrachten/a1', { viewer_relations: ['owner'] });
    await tabs(owner.container);
    expect(allText(owner.container)).toContain('Je bent eigenaar');
    owner.unmount();
    const admin = renderShell(PERMISSIONS.lezer, '/opdrachten/a1', {
      viewer_relations: ['function:lezer', 'function:beheerder'],
    });
    await tabs(admin.container);
    expect(allText(admin.container)).toContain('Je bekijkt als beheerder');
  });

  it('labels a potential assignment as such', async () => {
    const { container } = renderShell(PERMISSIONS.owner, '/opdrachten/a1', {
      phase: 'potential',
      status: 'draft',
    });
    await tabs(container);
    expect(container.textContent).toContain('Potentiële opdracht');
    expect(container.querySelector('nldd-badge[text="In voorbereiding"]')).not.toBeNull();
  });
});

describe('Bemensing tab', () => {
  const tabOf = (container: HTMLElement) =>
    container.querySelectorAll('nldd-simple-section')[1] as HTMLElement;

  it('draws the roles as a timeline: the demand as a frame, people as bars, the gap as open', async () => {
    const { container } = renderShell(PERMISSIONS.planner, '/opdrachten/a1/bemensing');
    await waitFor(() => expect(container.querySelector('table[role="grid"]')).not.toBeNull());
    const tab = tabOf(container);
    expect(tab.querySelector('[data-bar="demand-l1"]')).toHaveAttribute('data-demand');
    expect(tab.querySelector('[data-bar="x1"]')?.textContent).toContain('Voorbeeld Een');
    const gap = tab.querySelector('[data-bar="gap-l1-2026-10-01"]')!;
    expect(gap).toHaveAttribute('data-open');
    expect(gap.textContent).toContain('0,3 FTE open');
    // The row label is quiet: the role with the asked FTE as a small figure.
    expect(tab.querySelector('.grip-board__name')?.textContent).toBe('Productmanager0,8 FTE');
    expect(tab.querySelector('.grip-board__attention')?.textContent).toContain(
      '0,3 FTE open vanaf okt',
    );
    expect(tab.querySelectorAll('h2, h3')).toHaveLength(0);
  });

  it('gives the answer first and shows no amount at all', async () => {
    const { container } = renderShell(PERMISSIONS.planner, '/opdrachten/a1/bemensing');
    await waitFor(() => expect(container.querySelector('table[role="grid"]')).not.toBeNull());
    const text = allText(tabOf(container));
    // One sentence of state, not three boxes.
    expect(text).toContain('De rol is nog open: Productmanager, 0,3 FTE vanaf oktober 2026.');
    expect(
      tabOf(container).querySelector('nldd-table[accessible-label="Hoe de rollen ervoor staan"]'),
    ).toBeNull();
    // The double booking is one signal: who, when, how much, and where to look.
    expect(text).toContain('Voorbeeld Een zit in oktober 2026 op 140%.');
    expect(tabOf(container).querySelector('nldd-link[href="/team/p1"]')).not.toBeNull();
    expect(text).toContain('andere categorie');
    expect(text).toContain('start op 1 dec 2026');
    expect(text).not.toContain('€');
    // The board is a quiet action in the bar, not a loose link.
    expect(tabOf(container).querySelector('nldd-link[href="/inzet?opdracht=a1"]')).toBeNull();
    // The legend names only what the picture shows.
    const legend = [...tabOf(container).querySelectorAll('.grip-board__legend li')].map(
      (li) => li.textContent,
    );
    expect(legend.some((item) => item?.includes('Niet inzetbaar'))).toBe(false);
    expect(legend.length).toBeLessThanOrEqual(6);
  });

  it('is the same picture for an owner, plus the ways to act', async () => {
    const { container } = renderShell(PERMISSIONS.owner, '/opdrachten/a1/bemensing');
    await waitFor(() => expect(container.querySelector('table[role="grid"]')).not.toBeNull());
    const tab = tabOf(container);
    expect(allText(tab)).not.toContain('€');
    expect(tab.querySelector('nldd-button[text="Nieuwe inzet"]')).not.toBeNull();
    // The open stretch proposes an inzet for exactly that gap.
    fireEvent.click(tab.querySelector('[data-bar="gap-l1-2026-10-01"]')!);
    await waitFor(() => expect(document.querySelector('nldd-sheet[open]')).not.toBeNull());
    const dates = [...document.querySelectorAll('nldd-sheet[open] nldd-date-field')].map((f) =>
      f.getAttribute('value'),
    );
    expect(dates).toEqual(['2026-10-01', '2026-12-31']);
  });

  it('shows a team member names per role and nothing of time', async () => {
    const { container } = renderShell(
      PERMISSIONS.member,
      '/opdrachten/a1/bemensing',
      {},
      NAMES_ONLY,
    );
    await waitFor(() =>
      expect(
        container.querySelector('nldd-table[accessible-label="Wie op welke rol zit"]'),
      ).not.toBeNull(),
    );
    const tab = tabOf(container);
    expect(tab.querySelector('table[role="grid"]')).toBeNull();
    expect(allText(tab)).toContain('Voorbeeld Een');
    expect(allText(tab)).not.toContain('%');
    // Looking without changing is said once, with who can.
    expect(allText(tab)).toContain(
      'Je kunt de bemensing bekijken. Wijzigen kan de eigenaar (Voorbeeld Eigenaar), een manager of een planner.',
    );
  });

  it('leads an empty assignment to the budget, or says whose turn it is', async () => {
    const empty = { ...NAMES_ONLY, roles: [] };
    const owner = renderShell(
      PERMISSIONS.owner,
      '/opdrachten/a1/bemensing',
      { phase: 'potential', status: 'draft' },
      empty,
    );
    await waitFor(() =>
      expect(owner.container.querySelector('nldd-button[text="Maak de begroting"]')).not.toBeNull(),
    );
    // Nothing to put a person on, so no way to add inzet and no notice about it.
    expect(owner.container.querySelector('nldd-button[text="Nieuwe inzet"]')).toBeNull();
    expect(owner.container.querySelector('nldd-banner[text="Inzet onder voorbehoud"]')).toBeNull();
    owner.unmount();

    const planner = renderShell(PERMISSIONS.planner, '/opdrachten/a1/bemensing', {}, empty);
    await waitFor(() =>
      expect(
        planner.container.querySelector(
          'nldd-inline-dialog[text="Deze opdracht heeft nog geen rollen"]',
        ),
      ).toHaveAttribute(
        'supporting-text',
        expect.stringContaining('Voorbeeld Eigenaar maakt eerst de begroting'),
      ),
    );
    expect(planner.container.querySelector('nldd-button[text="Maak de begroting"]')).toBeNull();
  });

  it('says inzet on a potential assignment is tentative', async () => {
    const { container } = renderShell(PERMISSIONS.planner, '/opdrachten/a1/bemensing', {
      phase: 'potential',
      status: 'quoted',
    });
    await waitFor(() =>
      expect(container.querySelector('nldd-banner[text="Inzet onder voorbehoud"]')).not.toBeNull(),
    );
  });
});

// Keeps the fixture honest: the figures used above are the ones in the header.
/** The course of the assignment as the server would give it. */
function courseWith(next: Record<string, unknown> | null, ended: string | null = null) {
  const labels = ['Begroting', 'Offerte', 'Aanbieden', 'Akkoord'];
  return {
    '/api/tasks/cases/assignment/a1/course': {
      case_kind: 'assignment',
      case_id: 'a1',
      course: {
        key: 'akkoord',
        label: 'Naar een akkoord',
        steps: labels.map((label, index) => ({
          key: label,
          label,
          state: index === 0 ? 'done' : index === 1 ? 'current' : 'future',
        })),
        current_label: 'Offerte',
        position: '2 van 4',
        next,
        ended,
      },
      parts: [],
    },
  };
}

describe('where an assignment stands, in its head', () => {
  const potential = { phase: 'potential', status: 'draft' };
  const primaries = (container: HTMLElement) =>
    [...container.querySelectorAll('nldd-button[appearance="primary"]')].map((button) =>
      button.getAttribute('text'),
    );

  it('says what is next to who has the move, with that one step as the only accent', async () => {
    const { container } = renderShell(
      PERMISSIONS.owner,
      '/opdrachten/a1/bemensing',
      potential,
      STAFFING,
      finance(),
      courseWith({
        mine: true,
        headline: 'Maak de offerte',
        sentence: 'Maak de offerte voor Voorbeeldministerie uit de begroting.',
        action_text: 'Maak offerte',
        action_href: '/opdrachten/a1/offerte',
        due_on: '2026-10-15',
      }),
    );
    await waitFor(() =>
      expect(container.textContent).toContain('Maak de offerte voor Voorbeeldministerie'),
    );
    // The steps say their own state, so work done out of order shows as done.
    expect(
      [...container.querySelectorAll('nldd-step-bar-item')].map((item) => [
        item.getAttribute('text'),
        item.getAttribute('status'),
      ]),
    ).toEqual([
      ['Begroting', 'past'],
      ['Offerte', 'current'],
      ['Aanbieden', 'future'],
      ['Akkoord', 'future'],
    ]);
    expect(container.textContent).toContain('Vóór 15 okt 2026');
    // One filled accent on the page: the next step, in the head. The tab's
    // own main action steps back.
    await waitFor(() => expect(primaries(container)).toEqual(['Maak offerte']));
    // The course says where it stands; no status tag says it again.
    expect(container.querySelector('nldd-badge[text="Concept"]')).toBeNull();
    expect(container.textContent).toContain('Potentiële opdracht');
  });

  it('gives someone who waits the sentence and no button', async () => {
    const { container } = renderShell(
      PERMISSIONS.lezer,
      '/opdrachten/a1',
      potential,
      STAFFING,
      finance(),
      courseWith({
        mine: false,
        headline: 'De offerte',
        sentence:
          'Je wacht op Voorbeeld Eigenaar, die de offerte maakt. Jij hoeft nu niets te doen.',
        who: 'Voorbeeld Eigenaar',
      }),
    );
    await waitFor(() => expect(container.textContent).toContain('Je wacht op Voorbeeld Eigenaar'));
    expect(primaries(container)).toEqual([]);
  });

  it('leaves the button to the page when the reader already is where the step is done', async () => {
    const { container } = renderShell(
      PERMISSIONS.owner,
      '/opdrachten/a1/bemensing',
      potential,
      STAFFING,
      finance(),
      courseWith({
        mine: true,
        headline: 'Vul de rol in',
        sentence: 'Zet iemand in op de rol Productmanager.',
        action_text: 'Zet iemand in',
        action_href: '/opdrachten/a1/bemensing',
      }),
    );
    await waitFor(() => expect(container.textContent).toContain('Zet iemand in op de rol'));
    expect(container.querySelector('nldd-button[text="Zet iemand in"]')).toBeNull();
  });

  describe('while looking back at a moment', () => {
    const LIVE = courseWith({
      mine: true,
      headline: 'Maak de offerte',
      sentence: 'Maak de offerte voor Voorbeeldministerie uit de begroting.',
      action_text: 'Maak offerte',
      action_href: '/opdrachten/a1/offerte',
    });
    const CHRONICLE = {
      '/api/assignments/a1/chronicle/7': {
        moment: {
          seq: 7,
          occurred_at: '2026-11-03T13:02:00Z',
          fact: 'quote_issued',
          title: 'Offerte gemaakt',
          decision: false,
          actor_name: null,
          actor_kind: 'system',
          effective_on: null,
          erased: false,
        },
        previous_seq: null,
        next_seq: null,
        assignment: {
          name: 'Opdracht Alfa 2026',
          status: 'draft',
          status_label: 'In voorbereiding',
          kind: 'external',
          owner_name: null,
          client_name: 'Eerdere opdrachtgever',
          start_date: '2025-02-01',
          end_date: '2025-03-31',
          notes: null,
          quote_date: null,
          verbal_agreement_note: null,
        },
        course: null,
        outside: [],
        later_known: [],
        restated: [],
        quotes: [],
        incomplete: false,
      },
      '/api/assignments/a1/chronicle': { items: [] },
    };
    const calls = () => (vi.mocked(fetch).mock.calls as unknown[][]).map((call) => String(call[0]));

    it('shows nothing live in the head, and does not ask for the live course', async () => {
      const { container } = renderShell(
        PERMISSIONS.owner,
        '/opdrachten/a1/geschiedenis?moment=7',
        { phase: 'closed', status: 'rejected' },
        STAFFING,
        finance(),
        { ...LIVE, ...CHRONICLE },
      );
      await tabs(container);
      await waitFor(() => expect(calls()).toContain('/api/assignments/a1/chronicle/7'));
      expect(calls().some((url) => url.startsWith('/api/tasks/cases/'))).toBe(false);
      expect(calls().some((url) => url.startsWith('/api/assignments/a1/financial'))).toBe(false);
      expect(container.textContent).not.toContain('Maak de offerte');
      expect(container.querySelector('nldd-step-bar')).toBeNull();
      expect(primaries(container)).toEqual([]);
      expect(container.querySelector('dl[aria-label^="Kerncijfers"]')).toBeNull();
      // The status of now would read as the status at that moment; the tab has its own.
      await waitFor(() => expect(allText(container)).toContain('In voorbereiding'));
      expect(container.querySelectorAll('nldd-badge')).toHaveLength(1);
      expect(container.querySelector('nldd-badge[text="Afgewezen"]')).toBeNull();
      // Of now only as who the reader looks stays; the stand says for whom and when.
      await waitFor(() => expect(allText(container)).toContain('Eerdere opdrachtgever'));
      const text = allText(container);
      expect(text).toContain('1 feb 2025 t/m 31 mrt 2025');
      expect(text).not.toContain('Voorbeeldministerie');
      expect(text).not.toContain('1 jan 2026');
      // The name is the one in the title, so the stand does not say it again.
      expect(text).not.toContain('Naam');
    });

    it('keeps as who the reader looks in the head, and nothing live beside it', async () => {
      const { container } = renderShell(
        PERMISSIONS.owner,
        '/opdrachten/a1/geschiedenis?moment=7',
        { phase: 'potential', viewer_relations: ['owner'] },
        STAFFING,
        finance(),
        CHRONICLE,
      );
      await tabs(container);
      await waitFor(() => expect(allText(container)).toContain('Eerdere opdrachtgever'));
      const line = [...container.querySelectorAll('nldd-text[color="secondary"]')].map(
        (element) => element.textContent,
      );
      expect(line).toContain('Je bent eigenaar');
      expect(allText(container)).not.toContain('Potentiële opdracht');
    });

    it('names the assignment in the stand only when it was called otherwise', async () => {
      const { container } = renderShell(
        PERMISSIONS.owner,
        '/opdrachten/a1/geschiedenis?moment=7',
        { name: 'Nieuwe naam nu' },
        STAFFING,
        finance(),
        CHRONICLE,
      );
      await waitFor(() => expect(allText(container)).toContain('Naam'));
      expect(allText(container)).toContain('Opdracht Alfa 2026');
    });

    it('leaves no empty line in the head for a reader without a relation', async () => {
      const { container } = renderShell(
        PERMISSIONS.owner,
        '/opdrachten/a1/geschiedenis?moment=7',
        { viewer_relations: [] },
        STAFFING,
        finance(),
        CHRONICLE,
      );
      await tabs(container);
      await waitFor(() => expect(allText(container)).toContain('Eerdere opdrachtgever'));
      expect(container.querySelector('nldd-container[layout="wrap"][gap="8"]')).toBeNull();
    });

    it('does not draw a course it still has from before', async () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
      });
      queryClient.setQueryData(
        COURSE_KEYS.one('assignment', 'a1'),
        LIVE['/api/tasks/cases/assignment/a1/course'],
      );
      mockApi({
        ...CHRONICLE,
        '/api/assignments/a1/financial': finance(),
        '/api/assignments/a1': assignment({ permissions: PERMISSIONS.owner }),
      });
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/opdrachten/a1/geschiedenis?moment=7']}>
            <Routes>
              <Route path="/opdrachten/:assignmentId" element={<AssignmentLayout />}>
                <Route path="geschiedenis" element={<p>geschiedenis</p>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      await waitFor(() => expect(container.textContent).toContain('geschiedenis'));
      expect(container.textContent).not.toContain('Maak de offerte');
      expect(container.querySelector('nldd-step-bar')).toBeNull();
      expect(primaries(container)).toEqual([]);
    });

    it('stays live for a moment in the address of another tab', async () => {
      const { container } = renderShell(
        PERMISSIONS.owner,
        '/opdrachten/a1/bemensing?moment=7',
        potential,
        STAFFING,
        finance(),
        LIVE,
      );
      await waitFor(() => expect(container.textContent).toContain('Maak de offerte'));
      expect(container.querySelector('nldd-step-bar')).not.toBeNull();
    });

    it('stays live on the tab without a moment', async () => {
      const { container } = renderShell(
        PERMISSIONS.owner,
        '/opdrachten/a1/geschiedenis',
        potential,
        STAFFING,
        finance(),
        { ...LIVE, ...CHRONICLE },
      );
      await waitFor(() => expect(container.textContent).toContain('Maak de offerte'));
      expect(container.querySelector('nldd-step-bar')).not.toBeNull();
    });
  });

  describe('a step taken in the head', () => {
    const posted = () =>
      (vi.mocked(fetch).mock.calls as unknown[][])
        .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
        .map(([url, init]) => [String(url), JSON.parse(String((init as RequestInit).body))]);
    const asked = (url: string) =>
      (vi.mocked(fetch).mock.calls as unknown[][]).filter(([called]) => String(called) === url)
        .length;
    const starting = (taskKey: string) =>
      courseWith({
        mine: true,
        task_key: taskKey,
        headline: 'Start de opdracht',
        sentence: 'Een interne opdracht heeft geen offerte nodig.',
        action_text: 'Start de opdracht',
        action_href: '/opdrachten/a1',
      });
    const click = async (container: HTMLElement) => {
      await waitFor(() =>
        expect(container.querySelector('nldd-button[text="Start de opdracht"]')).not.toBeNull(),
      );
      fireEvent.click(container.querySelector('nldd-button[text="Start de opdracht"]')!);
      await waitFor(() => expect(posted().length).toBeGreaterThan(0));
    };

    it('starts an internal assignment in one step, with no agreement in between', async () => {
      const { container } = renderShell(
        PERMISSIONS.owner,
        '/opdrachten/a1',
        {
          kind: 'internal',
          status: 'draft',
          phase: 'potential',
          allowed_transitions: ['accepted', 'in_progress', 'cancelled'],
        },
        STAFFING,
        finance(),
        starting('intern.starten'),
      );
      await click(container);
      expect(posted()).toEqual([['/api/assignments/a1/transition', { target: 'in_progress' }]]);
    });

    it('goes to where the step is done when the assignment may not take it now', async () => {
      const { container } = renderShell(
        PERMISSIONS.owner,
        '/opdrachten/a1/bemensing',
        { allowed_transitions: ['cancelled'] },
        STAFFING,
        finance(),
        starting('uitvoering.starten'),
      );
      await waitFor(() =>
        expect(container.querySelector('nldd-button[text="Start de opdracht"]')).not.toBeNull(),
      );
      fireEvent.click(container.querySelector('nldd-button[text="Start de opdracht"]')!);
      await waitFor(() => expect(container.textContent).toContain('overzicht'));
      expect(posted()).toEqual([]);
    });

    it('reads the moments again when the list stands under the head', async () => {
      const { container } = renderShell(
        PERMISSIONS.owner,
        '/opdrachten/a1/geschiedenis',
        { allowed_transitions: ['in_progress'] },
        STAFFING,
        finance(),
        {
          ...starting('uitvoering.starten'),
          '/api/assignments/a1/chronicle': { items: [] },
          '/api/events': { items: [], next_before: null },
        },
      );
      await waitFor(() => expect(asked('/api/assignments/a1/chronicle')).toBe(1));
      await click(container);
      await waitFor(() => expect(asked('/api/assignments/a1/chronicle')).toBe(2));
    });
  });

  it('shows how it ended and asks nothing once it has ended', async () => {
    const { container } = renderShell(
      PERMISSIONS.owner,
      '/opdrachten/a1',
      { phase: 'closed', status: 'rejected' },
      STAFFING,
      finance(),
      courseWith(null, 'Afgewezen'),
    );
    await waitFor(() => expect(container.querySelector('nldd-badge')).not.toBeNull());
    expect(container.querySelector('nldd-step-bar')).toBeNull();
    expect(primaries(container)).toEqual([]);
  });
});

it('uses the same figures in header and tab fixtures', () => {
  expect(finance().totals).toBe(FIGURES);
});
