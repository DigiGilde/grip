import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MainNavigation } from '@/layout/MainNavigation';
import { renderApp } from '@/test/utils';
import type { CaseTasks as CaseTasksData, Task } from './api';
import { AssignmentTasksTab } from './CaseTasks';
import { byDueGroup, closesBecause, dueGroup, endOfWeek, filterTasks, optionsOf } from './groups';
import { movesOf } from './moves';
import { TasksPage } from './TasksPage';

function task(overrides: Partial<Task>): Task {
  return {
    id: 't-1',
    case_kind: 'assignment',
    assignment_id: 'a-1',
    case_label: 'Opdracht Alfa 2026',
    title: 'Sluit september 2026 af',
    track: 'uitvoering',
    track_label: 'Uitvoering',
    status: 'todo',
    status_label: 'Te doen',
    origin: 'plan',
    assignee_label: 'Eigenaar of manager van de opdracht',
    link: '/opdrachten/a-1/maandafsluiting?maand=2026-09',
    is_mine: true,
    can_change: true,
    can_complete: false,
    closes_by_fact: true,
    closing_fact_label: 'de maand is afgesloten',
    ...overrides,
  };
}

const LATE = task({ id: 't-late', due_on: '2026-10-07', overdue: true });
const SOON = task({ id: 't-soon', title: 'Vul de rol Ontwerper in', due_on: '2026-10-09' });
const MANUAL = task({
  id: 't-manual',
  title: 'Bel de opdrachtgever',
  origin: 'manual',
  can_complete: true,
  closes_by_fact: false,
  closing_fact_label: null,
  assignee_label: 'Fictieve Collega',
  is_mine: false,
  link: null,
});
const WAITING = task({
  id: 't-wait',
  title: 'Wacht op akkoord van de opdrachtgever',
  status: 'waiting',
  status_label: 'Wacht op een ander',
  waiting_on: 'de opdrachtgever',
  track_label: 'Offerte',
  case_label: 'Opdracht Beta 2026',
});

/** Answers GET requests from a table of path to body; anything else is a 404. */
function stubApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split('?')[0] ?? '';
      const found = path in routes;
      return new Response(JSON.stringify(found ? routes[path] : { title: 'Niet gevonden' }), {
        status: found ? 200 : 404,
        headers: { 'Content-Type': found ? 'application/json' : 'application/problem+json' },
      });
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('grouping', () => {
  const thursday = new Date(2026, 9, 8);

  it('ends the week on Sunday', () => {
    expect(endOfWeek(thursday)).toBe('2026-10-11');
    expect(endOfWeek(new Date(2026, 9, 11))).toBe('2026-10-11');
  });

  it('sorts tasks into too late, this week and later', () => {
    expect(dueGroup(LATE, thursday)).toBe('overdue');
    expect(dueGroup(SOON, thursday)).toBe('thisWeek');
    expect(dueGroup(task({ due_on: '2026-10-12' }), thursday)).toBe('later');
    expect(dueGroup(task({ due_on: null }), thursday)).toBe('later');
    expect(byDueGroup([LATE, SOON], thursday).overdue).toEqual([LATE]);
  });

  it('filters the board on case, track and person', () => {
    const all = [LATE, MANUAL, WAITING];
    const none = { caseLabel: '', track: '', assignee: '' };
    expect(filterTasks(all, none)).toHaveLength(3);
    expect(filterTasks(all, { ...none, caseLabel: 'Opdracht Beta 2026' })).toEqual([WAITING]);
    expect(filterTasks(all, { ...none, track: 'Offerte' })).toEqual([WAITING]);
    expect(filterTasks(all, { ...none, assignee: 'mine' })).toEqual([LATE, WAITING]);
    expect(filterTasks(all, { ...none, assignee: 'Fictieve Collega' })).toEqual([MANUAL]);
    expect(optionsOf(all, (item) => item.track_label, 'Alle sporen').map((o) => o.label)).toEqual([
      'Alle sporen',
      'Offerte',
      'Uitvoering',
    ]);
  });
});

describe('what a task allows', () => {
  it('cannot be ticked when a fact closes it, and says which fact', () => {
    expect(movesOf(LATE).map((move) => move.text)).toEqual(['Begin', 'Wacht op een ander']);
    expect(closesBecause(LATE)).toBe('Sluit vanzelf zodra de maand is afgesloten.');
  });

  it('can be ticked when it is a task of your own', () => {
    expect(movesOf(MANUAL).map((move) => move.text)).toContain('Rond af');
    expect(closesBecause(MANUAL)).toBeNull();
  });

  it('offers nothing to a reader who may not change it', () => {
    expect(movesOf({ ...MANUAL, can_change: false })).toEqual([]);
  });
});

describe('TasksPage', () => {
  it('shows my tasks with the late ones first', async () => {
    stubApi({ '/api/tasks/mine': { items: [SOON, LATE], counts: { open: 2, to_do: 2, overdue: 1 } } });
    const { container } = renderApp(<TasksPage />, { path: '/taken' });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Taken');
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const headings = [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
      el.getAttribute('text'),
    );
    expect(headings[0]).toBe('Te laat');
    expect(container.querySelector('nldd-table')).toHaveAttribute('accessible-label', 'Te laat');
    // Nothing is open by default.
    expect(container.ownerDocument.querySelector('nldd-sheet[open]')).toBeNull();
  });

  it('says so when there is nothing to do', async () => {
    stubApi({ '/api/tasks/mine': {} });
    const { container } = renderApp(<TasksPage />, { path: '/taken' });
    await waitFor(() =>
      expect(container.querySelector('[text="Niets te doen"]')).not.toBeNull(),
    );
  });

  it('draws the board in four columns and explains a task that closes by itself', async () => {
    stubApi({ '/api/tasks': { items: [LATE, MANUAL, WAITING] } });
    const { container } = renderApp(<TasksPage />, { path: '/taken?weergave=bord' });
    await waitFor(() => expect(container.querySelectorAll('nldd-card')).toHaveLength(3));
    const columns = [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
      el.getAttribute('text'),
    );
    expect(columns).toEqual(['Te doen (2)', 'Bezig (0)', 'Wacht op een ander (1)', 'Klaar (0)']);
    expect(container).toHaveTextContent('Sluit vanzelf zodra de maand is afgesloten.');
    expect(container).toHaveTextContent('Wacht op de opdrachtgever');
    // Every card opens by a link and moves by a menu: no dragging needed.
    const link = container.querySelector('nldd-card nldd-link');
    expect(link).toHaveAttribute('href', '/taken?weergave=bord&taak=t-late');
    expect(container.querySelectorAll('nldd-card nldd-icon-button')).toHaveLength(3);
  });

  it('opens the task named in the address', async () => {
    stubApi({
      '/api/tasks/mine': { items: [LATE] },
      '/api/tasks/t-late': { ...LATE, notes: [{ id: 'n-1', body: 'Uren nog niet compleet.', created_at: '2026-10-08T09:00:00Z', author_name: 'Fictieve Collega' }] },
    });
    renderApp(<TasksPage />, { path: '/taken?taak=t-late' });
    await waitFor(() => expect(document.body).toHaveTextContent('Uren nog niet compleet.'));
    expect(document.querySelector('nldd-sheet')).toHaveAttribute('open');
    expect(document.body).toHaveTextContent('Sluit vanzelf zodra de maand is afgesloten.');
  });
});

describe('the Taken tab of a case', () => {
  const CASE: CaseTasksData = {
    case_kind: 'assignment',
    case_id: 'a-1',
    plan_version: '2026.1',
    can_add: true,
    tracks: [
      { key: 'offerte', label: 'Offerte', open_count: 0, waiting_count: 0, standing: 'Niets te doen', tasks: [] },
      { key: 'uitvoering', label: 'Uitvoering', open_count: 1, waiting_count: 0, standing: LATE.title, tasks: [LATE] },
    ],
  };

  function renderTab(body: CaseTasksData) {
    stubApi({ '/api/tasks/cases/assignment/a-1': body });
    return renderApp(
      <Routes>
        <Route path="/opdrachten/:assignmentId/taken" element={<AssignmentTasksTab />} />
      </Routes>,
      { path: '/opdrachten/a-1/taken' },
    );
  }

  it('shows where each track stands and the tasks per track', async () => {
    const { container } = renderTab(CASE);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const standing = container.querySelector('nldd-list[accessible-label="Stand per spoor"]');
    expect(standing?.querySelectorAll('nldd-list-item')).toHaveLength(2);
    expect(container.querySelectorAll('nldd-table')).toHaveLength(1);
    expect(container.querySelector('nldd-button[text="Nieuwe taak"]')).not.toBeNull();
  });

  it('offers no new task to a reader who may only read', async () => {
    const { container } = renderTab({ ...CASE, can_add: false });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-button[text="Nieuwe taak"]')).toBeNull();
  });
});

describe('the navigation', () => {
  it('carries the number of my open tasks', async () => {
    stubApi({ '/api/tasks/count': { open: 3, to_do: 2, overdue: 1 } });
    const { container } = renderApp(<MainNavigation />, { path: '/' });
    await waitFor(() =>
      expect(container.querySelector('nldd-tab-bar-item[href="/taken"]')).toHaveAttribute(
        'text',
        'Taken (3)',
      ),
    );
  });

  it('shows the plain word when there is nothing', async () => {
    stubApi({ '/api/tasks/count': {} });
    const { container } = renderApp(<MainNavigation />, { path: '/' });
    expect(container.querySelector('nldd-tab-bar-item[href="/taken"]')).toHaveAttribute('text', 'Taken');
  });
});
