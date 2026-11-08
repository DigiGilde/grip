import { fireEvent, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { Button } from '@/ui/Button';
import type { AssignmentPermissions } from './api';
import { AssignmentLanding } from './AssignmentLanding';
import { AssignmentLayout } from './AssignmentLayout';
import { AssignmentPartPage } from './AssignmentPartPage';
import { DetailsPart } from './parts/DetailsPart';
import { TasksPart } from './parts/TasksPart';
import { TeamPart } from './parts/TeamPart';
import type { AssignmentParts } from './partsApi';
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

const ROWS: AssignmentParts['parts'] = [
  { key: 'close', label: 'Afsluiten en factureren', notice: '8 maanden af te sluiten' },
  { key: 'budget', label: 'Begroting', notice: '1 regel over de begroting' },
  { key: 'quote', label: 'Offerte', notice: 'Getekend op 18 dec 2025' },
  { key: 'team', label: 'Team', notice: null },
  { key: 'details', label: 'Gegevens', notice: 'Eigenaar Voorbeeld Eigenaar' },
  { key: 'history', label: 'Geschiedenis', notice: null },
];

function parts(overrides: Partial<AssignmentParts> = {}): AssignmentParts {
  return {
    assignment_id: 'a1',
    parts: ROWS,
    tasks_link: true,
    is_client: false,
    own_line: null,
    ...overrides,
  };
}

interface ShellOptions {
  permissions?: AssignmentPermissions;
  path?: string;
  detail?: object;
  rows?: Partial<AssignmentParts>;
  staffing?: unknown;
  money?: unknown;
  extra?: Record<string, unknown>;
}

function renderShell({
  permissions = PERMISSIONS.owner,
  path = '/opdrachten/a1',
  detail = {},
  rows = {},
  staffing = STAFFING,
  money = finance(),
  extra = {},
}: ShellOptions = {}) {
  mockApi({
    ...extra,
    '/api/assignments/a1/parts': parts(rows),
    '/api/assignments/a1/financial': money,
    '/api/assignments/a1/staffing': staffing,
    '/api/allocations/options': { people: [], lines: [] },
    '/api/assignments/a1': assignment({ permissions, ...detail }),
    '/api/vacancies': [],
  });
  return renderApp(
    <Routes>
      <Route path="/opdrachten/:assignmentId" element={<AssignmentLayout />}>
        <Route index element={<AssignmentLanding />} />
        <Route path="team" element={<TeamPart />} />
        <Route path="gegevens" element={<DetailsPart />} />
        <Route path="taken" element={<TasksPart />} />
        <Route
          path="rapport"
          element={
            <AssignmentPartPage part="report" kind="worksheet">
              <span>Inhoud</span>
            </AssignmentPartPage>
          }
        />
        <Route
          path="afsluiten"
          element={
            <AssignmentPartPage part="close" kind="worksheet">
              <Button appearance="primary" text="Eigen knop" />
            </AssignmentPartPage>
          }
        />
        <Route
          path="offerte"
          element={
            <AssignmentPartPage part="quote" kind="document">
              <Button appearance="primary" text="Eigen knop" />
            </AssignmentPartPage>
          }
        />
      </Route>
    </Routes>,
    { path },
  );
}

const rowTexts = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-list[accessible-label^="Onderdelen"] nldd-text-cell')].map(
    (cell) => cell.getAttribute('text'),
  );

const primaries = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-button[appearance="primary"]')].map((button) =>
    button.getAttribute('text'),
  );

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

const CLOSE_MARCH = {
  mine: true,
  part: 'acts',
  headline: 'Sluit maart 2026 af',
  sentence: 'Stel vast wie in maart 2026 hoeveel heeft gewerkt, en sluit de maand af.',
  action_text: 'Sluit maart 2026 af',
  action_href: '/opdrachten/a1/afsluiten?maand=2026-03',
  task_key: 'uitvoering.maand_afsluiten',
};

describe('the landing of an assignment', () => {
  it('shows the rows of the answer, in its order, each with what it says', async () => {
    const { container } = renderShell();
    await waitFor(() => expect(rowTexts(container)).toHaveLength(6));
    expect(rowTexts(container)).toEqual([
      'Afsluiten en factureren',
      'Begroting',
      'Offerte',
      'Team',
      'Gegevens',
      'Geschiedenis',
    ]);
    const list = container.querySelector('nldd-list[accessible-label^="Onderdelen"]')!;
    const items = [...list.querySelectorAll('nldd-list-item')];
    expect(items[0]).toHaveAttribute('href', '/opdrachten/a1/afsluiten');
    expect(items[0]?.querySelector('nldd-text-cell')).toHaveAttribute(
      'supporting-text',
      '8 maanden af te sluiten',
    );
    expect(items[3]?.querySelector('nldd-text-cell')).not.toHaveAttribute('supporting-text');
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
  });

  it('shows no row the server left out', async () => {
    const { container } = renderShell({
      permissions: PERMISSIONS.member,
      rows: {
        parts: [
          { key: 'team', label: 'Team', notice: null },
          { key: 'details', label: 'Gegevens', notice: 'Eigenaar Voorbeeld Eigenaar' },
          { key: 'history', label: 'Geschiedenis', notice: null },
        ],
      },
    });
    await waitFor(() => expect(rowTexts(container)).toEqual(['Team', 'Gegevens', 'Geschiedenis']));
  });

  it('has its name as the h1 and the document title, and goes back to the list', async () => {
    const { container } = renderShell();
    await waitFor(() =>
      expect(container.querySelector('h1')).toHaveTextContent('Opdracht Alfa 2026'),
    );
    expect(document.title).toContain('Opdracht Alfa 2026');
    expect(allText(container)).toContain('Terug naar Opdrachten');
  });

  it('shows who is on the team their own line above the rows', async () => {
    const { container } = renderShell({
      permissions: PERMISSIONS.member,
      rows: { own_line: 'Developer, 100%, tot 31 dec 2026', tasks_link: false },
    });
    await waitFor(() => expect(rowTexts(container).length).toBeGreaterThan(0));
    expect(container.textContent).toContain('Jij: Developer, 100%, tot 31 dec 2026');
    expect(container.querySelector('nldd-link[text="Alle taken van deze opdracht"]')).toBeNull();
  });

  it('shows no line of its own to who has no work on it', async () => {
    const { container } = renderShell();
    await waitFor(() => expect(rowTexts(container)).toHaveLength(6));
    expect(container.textContent).not.toContain('Jij:');
  });

  it('leads who runs the assignment to all its tasks', async () => {
    const { container } = renderShell();
    await waitFor(() =>
      expect(
        container.querySelector('nldd-link[text="Alle taken van deze opdracht"]'),
      ).toHaveAttribute('href', '/opdrachten/a1/taken'),
    );
  });

  it('has one link to the tasks: "En nog N taken voor jou" when there is such a line', async () => {
    const { container } = renderShell({
      extra: courseWith(CLOSE_MARCH),
    });
    await waitFor(() => expect(rowTexts(container)).toHaveLength(6));
    expect(container.querySelectorAll('nldd-link[href="/opdrachten/a1/taken"]')).toHaveLength(1);
    expect(container.querySelector('nldd-link[text="Alle taken van deze opdracht"]')).not.toBeNull();
    vi.unstubAllGlobals();
    const more = renderShell({
      extra: {
        '/api/tasks/cases/assignment/a1/course': {
          ...courseWith(CLOSE_MARCH)['/api/tasks/cases/assignment/a1/course'],
          course: {
            ...courseWith(CLOSE_MARCH)['/api/tasks/cases/assignment/a1/course'].course,
            more_to_do: 2,
          },
        },
      },
    });
    await waitFor(() =>
      expect(more.container.querySelector('nldd-link[text="En nog 2 taken voor jou"]')).not.toBeNull(),
    );
    expect(more.container.querySelectorAll('nldd-link[href="/opdrachten/a1/taken"]')).toHaveLength(1);
    expect(more.container.querySelector('nldd-link[text="Alle taken van deze opdracht"]')).toBeNull();
  });

  it('says that the work is done while a closing step is still open, and Afgerond without one', async () => {
    const allDone = (next: Record<string, unknown> | null) => {
      const reply = courseWith(next)['/api/tasks/cases/assignment/a1/course'];
      return {
        '/api/tasks/cases/assignment/a1/course': {
          ...reply,
          course: {
            ...reply.course,
            steps: reply.course.steps.map((step) => ({ ...step, state: 'done' })),
            current_label: null,
          },
        },
      };
    };
    const open = renderShell({ detail: { status: 'completed' }, extra: allDone(CLOSE_MARCH) });
    await waitFor(() =>
      expect(open.container.textContent).toContain('Werk afgerond, afsluiten loopt nog.'),
    );
    expect(open.container.textContent).not.toContain('Afgerond.');
    open.unmount();
    vi.unstubAllGlobals();
    const done = renderShell({ detail: { status: 'completed' }, extra: allDone(null) });
    await waitFor(() =>
      expect(done.container.querySelector('[supporting-text$="Afgerond."]')).not.toBeNull(),
    );
    expect(done.container.innerHTML).not.toContain('afsluiten loopt nog');
  });

  it('shows three key figures, only to who may see money', async () => {
    const owner = renderShell();
    await waitFor(() =>
      expect(owner.container.querySelector('[aria-label^="Kerncijfers"]')).not.toBeNull(),
    );
    const text = allText(owner.container);
    expect(text).toContain('Begroot');
    expect(text).toContain('187.800');
    expect(text).toContain('Verwacht totaal');
    expect(text).toContain('Afwijking');
    expect(text).toContain('€ 21.300 (11,3%) ruimte');
    expect(text).not.toContain('Gerealiseerd');
    owner.unmount();

    const planner = renderShell({ permissions: PERMISSIONS.planner });
    await waitFor(() => expect(rowTexts(planner.container)).toHaveLength(6));
    expect(planner.container.querySelector('[aria-label^="Kerncijfers"]')).toBeNull();
    expect(allText(planner.container)).not.toContain('€');
  });

  it('shows no key figures on an assignment this instance asked for', async () => {
    const { container } = renderShell({ rows: { is_client: true } });
    await waitFor(() => expect(rowTexts(container)).toHaveLength(6));
    expect(container.querySelector('[aria-label^="Kerncijfers"]')).toBeNull();
    expect(allText(container)).not.toContain('Begroot');
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
    const { container } = renderShell({ money: finance({ totals: empty }) });
    await waitFor(() => expect(rowTexts(container)).toHaveLength(6));
    expect(container.querySelector('[aria-label^="Kerncijfers"]')).toBeNull();
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
    const { container } = renderShell({
      detail: { start_date: '2027-01-01', end_date: '2027-12-31' },
      money: finance({ totals: later }),
    });
    await waitFor(() =>
      expect(container.querySelector('[aria-label^="Kerncijfers"]')).not.toBeNull(),
    );
    const text = allText(container);
    expect(text).toContain('434.400');
    expect(text).toContain('Nog geen inzet gepland');
    expect(text).not.toContain('ruimte');
    expect(text).not.toContain('100');
    const calls = (vi.mocked(fetch).mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(calls).toContain('/api/assignments/a1/financial?year=all');
  });

  it('says for whom and when, and that it is potential, in words', async () => {
    const { container } = renderShell({ detail: { phase: 'potential', status: 'draft' } });
    await waitFor(() => expect(rowTexts(container)).toHaveLength(6));
    expect(container.querySelector('nldd-title')?.getAttribute('supporting-text')).toContain(
      'Potentiële opdracht. Voorbeeldministerie, 1 jan',
    );
    expect(container.querySelector('nldd-badge')).toBeNull();
  });

  it('gives the course one line and the next step the one button', async () => {
    const { container } = renderShell({ extra: courseWith(CLOSE_MARCH) });
    await waitFor(() => expect(primaries(container)).toEqual(['Sluit maart 2026 af']));
    expect(container.textContent).toContain('Offerte, daarna aanbieden.');
    expect(container.textContent).toContain('Stel vast wie in maart 2026');
    expect(container.querySelector('nldd-step-bar')).toBeNull();
  });

  it('does a step that is one decision in place', async () => {
    const { container } = renderShell({
      detail: { allowed_transitions: ['in_progress'] },
      extra: courseWith({
        mine: true,
        part: 'acts',
        headline: 'Start de uitvoering',
        sentence: 'De opdrachtgever heeft getekend. Start de uitvoering.',
        action_text: 'Start de uitvoering',
        action_href: '/opdrachten/a1',
        task_key: 'uitvoering.starten',
      }),
    });
    await waitFor(() => expect(primaries(container)).toEqual(['Start de uitvoering']));
  });

  it('gives someone who waits the sentence and no button', async () => {
    const { container } = renderShell({
      permissions: PERMISSIONS.lezer,
      rows: { tasks_link: false },
      extra: courseWith({
        mine: false,
        part: 'watches',
        headline: 'De offerte',
        sentence: 'Voorbeeld Eigenaar is aan zet: de offerte.',
        who: 'Voorbeeld Eigenaar',
      }),
    });
    await waitFor(() => expect(container.textContent).toContain('Voorbeeld Eigenaar is aan zet'));
    expect(primaries(container)).toEqual([]);
  });

  it('never says there is nothing to do while the reader has a task on another line', async () => {
    const { container } = renderShell({
      extra: {
        ...courseWith({
          mine: false,
          part: 'waits',
          headline: 'Het aanbieden',
          sentence: 'Je wacht op Voorbeeld Eigenaar. Jij hoeft nu niets te doen.',
          who: 'Voorbeeld Eigenaar',
          may_take_over: true,
          task_id: 't0',
        }),
        '/api/tasks/cases/assignment/a1': {
          case_kind: 'assignment',
          case_id: 'a1',
          plan_version: '1',
          can_add: true,
          tracks: [
            {
              key: 'bemensing',
              label: 'Rollen',
              open_count: 1,
              waiting_count: 0,
              standing: '',
              tasks: [
                {
                  id: 't1',
                  title: 'Vul de rol Developer in',
                  headline: 'Vul de rol Developer in',
                  instruction: 'De rol Developer is nog niet ingevuld. Plan iemand in.',
                  needs_me: true,
                  action_text: 'Vul de rol in',
                  work_href: '/opdrachten/a1/team',
                },
              ],
            },
          ],
        },
      },
    });
    await waitFor(() => expect(primaries(container)).toEqual(['Vul de rol in']));
    expect(container.textContent).toContain('De rol Developer is nog niet ingevuld');
    expect(allText(container)).not.toContain('Jij hoeft nu niets te doen');
    expect(container.querySelector('nldd-button[text="Neem deze stap over"]')).toBeNull();
  });

  it('shows how it ended and asks nothing once it has ended', async () => {
    const { container } = renderShell({
      detail: { phase: 'closed', status: 'rejected' },
      extra: courseWith(null, 'Afgewezen'),
    });
    await waitFor(() => expect(rowTexts(container)).toHaveLength(6));
    expect(container.querySelector('nldd-title')?.getAttribute('supporting-text')).toContain(
      'Afgewezen.',
    );
    expect(primaries(container)).toEqual([]);
  });

  it('says an assignment does not exist instead of drawing a page around nothing', async () => {
    mockApi({});
    const { container } = renderApp(
      <Routes>
        <Route path="/opdrachten/:assignmentId" element={<AssignmentLayout />}>
          <Route index element={<AssignmentLanding />} />
        </Route>
      </Routes>,
      { path: '/opdrachten/a1' },
    );
    await waitFor(() => expect(allText(container)).toContain('Deze opdracht is niet gevonden'));
    expect(container.querySelector('nldd-list')).toBeNull();
  });
});

describe('a part of an assignment', () => {
  it('opens the report without a row for who reads the money, and says no to who does not', async () => {
    const owner = renderShell({ path: '/opdrachten/a1/rapport' });
    await waitFor(() => expect(owner.container.querySelector('h1')).toHaveTextContent('Rapport'));
    owner.unmount();
    vi.unstubAllGlobals();
    const planner = renderShell({ path: '/opdrachten/a1/rapport', permissions: PERMISSIONS.planner });
    await waitFor(() => expect(planner.container.querySelector('[data-state="no-access"]')).not.toBeNull());
  });

  it('has its own name as the h1 and the document title, and goes back to the assignment', async () => {
    const { container } = renderShell({ path: '/opdrachten/a1/team' });
    await waitFor(() => expect(container.querySelector('h1')).toHaveTextContent('Team'));
    expect(document.title).toContain('Team, Opdracht Alfa 2026');
    const text = allText(container);
    expect(text).toContain('Terug naar Opdracht Alfa 2026');
    expect(text).not.toContain('Terug naar Opdrachten');
    // The figures stand only on the landing.
    expect(container.querySelector('[aria-label^="Kerncijfers"]')).toBeNull();
  });

  it('switches to the other parts with the bar, in the order of the answer', async () => {
    const { container } = renderShell({ path: '/opdrachten/a1/team' });
    await waitFor(() => expect(container.querySelector('nldd-menu-bar')).not.toBeNull());
    const items = [...container.querySelectorAll('nldd-menu-bar-item')];
    expect(items.map((item) => item.getAttribute('text'))).toEqual(ROWS.map((row) => row.label));
    expect(items[0]).toHaveAttribute('href', '/opdrachten/a1/afsluiten');
    const current = container.querySelectorAll('nldd-menu-bar-item[current]');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute('text', 'Team');
    expect(container.querySelector('nldd-menu-bar')).toHaveAttribute(
      'accessible-label',
      'Onderdelen van Opdracht Alfa 2026',
    );
  });

  it('has no bar on a narrow screen: switching goes through the landing', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: true,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    const { container } = renderShell({ path: '/opdrachten/a1/team' });
    await waitFor(() => expect(container.querySelector('h1')).toHaveTextContent('Team'));
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
  });

  it('tells a reader who does not have the part so, and shows nothing of it', async () => {
    const { container } = renderShell({
      permissions: PERMISSIONS.member,
      path: '/opdrachten/a1/afsluiten',
      rows: { parts: ROWS.filter((row) => row.key !== 'close') },
    });
    await waitFor(() => expect(allText(container)).toContain('Je hebt hier geen toegang'));
    expect(container.querySelector('nldd-button[text="Eigen knop"]')).toBeNull();
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
    expect(allText(container)).toContain('Terug naar Opdracht Alfa 2026');
  });

  it('gives the next step to the head when it leads here, and the own button steps back', async () => {
    const { container } = renderShell({
      path: '/opdrachten/a1/afsluiten',
      extra: courseWith(CLOSE_MARCH),
    });
    await waitFor(() => expect(primaries(container)).toEqual(['Sluit maart 2026 af']));
    expect(container.querySelector('nldd-button[text="Eigen knop"]')).toHaveAttribute(
      'appearance',
      'secondary',
    );
  });

  it('shows no next step that belongs somewhere else', async () => {
    const { container } = renderShell({
      path: '/opdrachten/a1/offerte',
      extra: courseWith(CLOSE_MARCH),
    });
    await waitFor(() => expect(primaries(container)).toEqual(['Eigen knop']));
  });

  it('leaves the button to the part when the step only names it', async () => {
    const { container } = renderShell({
      path: '/opdrachten/a1/offerte',
      extra: courseWith({
        mine: true,
        part: 'acts',
        headline: 'Bied de offerte aan',
        sentence: 'Bied haar aan.',
        action_text: 'Bied de offerte aan',
        action_href: '/opdrachten/a1/offerte',
      }),
    });
    await waitFor(() => expect(primaries(container)).toEqual(['Eigen knop']));
  });

  it('does not say on a part that the reader only has to wait', async () => {
    const { container } = renderShell({
      path: '/opdrachten/a1/team',
      extra: courseWith({
        mine: false,
        part: 'waits',
        headline: 'De offerte',
        sentence: 'Je wacht op Voorbeeld Eigenaar. Jij hoeft nu niets te doen.',
      }),
    });
    await waitFor(() => expect(container.querySelector('h1')).toHaveTextContent('Team'));
    expect(allText(container)).not.toContain('Jij hoeft nu niets te doen');
  });

  it('puts Nieuwe taak in the head of all tasks, for who runs the assignment', async () => {
    const { container } = renderShell({
      path: '/opdrachten/a1/taken',
      extra: {
        '/api/tasks/cases/assignment/a1': {
          case_kind: 'assignment',
          case_id: 'a1',
          plan_version: '1',
          can_add: true,
          tracks: [],
        },
      },
    });
    await waitFor(() => expect(primaries(container)).toEqual(['Nieuwe taak']));
    expect(container.querySelector('h1')).toHaveTextContent('Alle taken van deze opdracht');
    expect(container.querySelector('.thing-action nldd-button')).toHaveAttribute(
      'text',
      'Nieuwe taak',
    );
  });

  it('gives all tasks only to who has the link', async () => {
    const { container } = renderShell({
      path: '/opdrachten/a1/taken',
      rows: { tasks_link: false },
    });
    await waitFor(() => expect(allText(container)).toContain('Je hebt hier geen toegang'));
  });
});

describe('Gegevens', () => {
  it('has one heading for its name and says how the reader sees the assignment', async () => {
    const owner = renderShell({
      path: '/opdrachten/a1/gegevens',
      detail: { viewer_relations: ['owner'] },
    });
    await waitFor(() => expect(owner.container.querySelector('h1')).toHaveTextContent('Gegevens'));
    expect(owner.container.querySelector('nldd-title[text="Gegevens"]')).toBeNull();
    expect(allText(owner.container)).toContain('Je bent eigenaar');
    owner.unmount();
    const admin = renderShell({
      permissions: PERMISSIONS.lezer,
      path: '/opdrachten/a1/gegevens',
      detail: { viewer_relations: ['function:lezer', 'function:beheerder'] },
    });
    await waitFor(() =>
      expect(allText(admin.container)).toContain('Je bekijkt deze opdracht als beheerder'),
    );
  });
});

describe('Team', () => {
  it('draws the roles as a timeline: the demand as a frame, people as bars, the gap as open', async () => {
    const { container } = renderShell({
      permissions: PERMISSIONS.planner,
      path: '/opdrachten/a1/team',
    });
    await waitFor(() => expect(container.querySelector('table[role="grid"]')).not.toBeNull());
    expect(container.querySelector('h1')).toHaveTextContent('Team');
    expect(container.querySelector('[data-bar="demand-l1"]')).toHaveAttribute('data-demand');
    expect(container.querySelector('[data-bar="x1"]')?.textContent).toContain('Voorbeeld Een');
    const gap = container.querySelector('[data-bar="gap-l1-2026-10-01"]')!;
    expect(gap).toHaveAttribute('data-open');
    expect(gap.textContent).toContain('0,3 FTE open');
    // The row label is quiet: the role with the asked FTE as a small figure.
    expect(container.querySelector('.grip-board__name')?.textContent).toBe('Productmanager0,8 FTE');
    expect(container.querySelector('.grip-board__attention')?.textContent).toContain(
      '0,3 FTE open vanaf okt',
    );
    expect(container.querySelectorAll('h2, h3')).toHaveLength(0);
  });

  it('gives the answer first and shows no amount at all', async () => {
    const { container } = renderShell({
      permissions: PERMISSIONS.planner,
      path: '/opdrachten/a1/team',
    });
    await waitFor(() => expect(container.querySelector('table[role="grid"]')).not.toBeNull());
    const text = allText(container);
    // One sentence of state, not three boxes.
    expect(text).toContain('De rol is nog open: Productmanager, 0,3 FTE vanaf oktober 2026.');
    expect(
      container.querySelector('nldd-table[accessible-label="Hoe de rollen ervoor staan"]'),
    ).toBeNull();
    // The double booking is one signal: who, when, how much, and where to look.
    expect(text).toContain('Voorbeeld Een zit in oktober 2026 op 140%.');
    expect(container.querySelector('nldd-link[href="/mensen/p1"]')).not.toBeNull();
    expect(text).toContain('andere categorie');
    expect(text).toContain('start op 1 dec 2026');
    expect(text).not.toContain('€');
    // The board is a quiet action in the bar, not a loose link.
    expect(container.querySelector('nldd-link[href="/mensen/bord?opdracht=a1"]')).toBeNull();
    expect(container.querySelector('nldd-button[href="/mensen/bord?opdracht=a1"]')).toHaveAttribute(
      'text',
      'Bekijk op het bord',
    );
    // The legend names only what the picture shows.
    const legend = [...container.querySelectorAll('.grip-board__legend li')].map(
      (li) => li.textContent,
    );
    expect(legend.some((item) => item?.includes('Niet inzetbaar'))).toBe(false);
    expect(legend.length).toBeLessThanOrEqual(6);
    expect(text.toLowerCase()).not.toContain('bemensing');
    expect(text).not.toContain('bord Inzet');
  });

  it('is the same picture for an owner, plus the ways to act', async () => {
    const { container } = renderShell({ path: '/opdrachten/a1/team' });
    await waitFor(() => expect(container.querySelector('table[role="grid"]')).not.toBeNull());
    expect(allText(container)).not.toContain('€');
    expect(container.querySelector('nldd-button[text="Nieuwe inzet"]')).not.toBeNull();
    // The open stretch proposes an inzet for exactly that gap.
    fireEvent.click(container.querySelector('[data-bar="gap-l1-2026-10-01"]')!);
    await waitFor(() => expect(document.querySelector('nldd-sheet[open]')).not.toBeNull());
    const dates = [...document.querySelectorAll('nldd-sheet[open] nldd-date-field')].map((f) =>
      f.getAttribute('value'),
    );
    expect(dates).toEqual(['2026-10-01', '2026-12-31']);
  });

  it('shows a team member names per role and nothing of time', async () => {
    const { container } = renderShell({
      permissions: PERMISSIONS.member,
      path: '/opdrachten/a1/team',
      staffing: NAMES_ONLY,
    });
    await waitFor(() =>
      expect(
        container.querySelector('nldd-table[accessible-label="Wie op welke rol zit"]'),
      ).not.toBeNull(),
    );
    expect(container.querySelector('table[role="grid"]')).toBeNull();
    expect(allText(container)).toContain('Voorbeeld Een');
    expect(allText(container)).not.toContain('%');
    // Looking without changing is said once, with who can.
    expect(allText(container)).toContain(
      'Je kunt het team bekijken. Wijzigen kan de eigenaar (Voorbeeld Eigenaar), een manager of een planner.',
    );
  });

  it('leads an empty assignment to the budget, or says whose turn it is', async () => {
    const empty = { ...NAMES_ONLY, roles: [] };
    const owner = renderShell({
      path: '/opdrachten/a1/team',
      detail: { phase: 'potential', status: 'draft' },
      staffing: empty,
    });
    await waitFor(() =>
      expect(owner.container.querySelector('nldd-button[text="Maak de begroting"]')).not.toBeNull(),
    );
    // Nothing to put a person on, so no way to add inzet and no notice about it.
    expect(owner.container.querySelector('nldd-button[text="Nieuwe inzet"]')).toBeNull();
    expect(owner.container.querySelector('nldd-banner[text="Inzet onder voorbehoud"]')).toBeNull();
    owner.unmount();

    const planner = renderShell({
      permissions: PERMISSIONS.planner,
      path: '/opdrachten/a1/team',
      staffing: empty,
    });
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
    const { container } = renderShell({
      permissions: PERMISSIONS.planner,
      path: '/opdrachten/a1/team',
      detail: { phase: 'potential', status: 'quoted' },
    });
    await waitFor(() =>
      expect(container.querySelector('nldd-banner[text="Inzet onder voorbehoud"]')).not.toBeNull(),
    );
  });
});
