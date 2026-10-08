import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MainNavigation } from '@/layout/MainNavigation';
import { renderApp, TEST_PERSON } from '@/test/utils';
import type { CaseTasks as CaseTasksData, Task } from './api';
import { AssignmentTasksTab } from './CaseTasks';
import { filterTasks, optionsOf } from './groups';
import { movesOf } from './moves';
import { MyTasksBlock } from './MyTasksBlock';
import { TaskBar } from './TaskBar';
import { TasksPage } from './TasksPage';
import { aboutLine, dueWords, goesToWork, myWork, workHref } from './telling';

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
    assignment_name: 'Opdracht Alfa 2026',
    headline: overrides.title ?? 'Sluit september 2026 af',
    instruction: 'Stel vast wie in september 2026 hoeveel heeft gewerkt, en sluit de maand af.',
    needs_me: true,
    why: 'September 2026 is voorbij en er was inzet gepland.',
    then: 'Daarna lever je de factuurgegevens aan.',
    action_text: 'Sluit september 2026 af',
    work_href: '/opdrachten/a-1/maandafsluiting?maand=2026-09',
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
  work_href: null,
  needs_me: false,
  action_text: null,
  instruction: 'Deze taak is van Fictieve Collega. Jij hoeft nu niets te doen.',
  why: null,
  then: null,
});
const WAITING = task({
  id: 't-wait',
  title: 'Wacht op akkoord van de opdrachtgever',
  headline: 'Akkoord van de opdrachtgever',
  instruction:
    'Je wacht op het akkoord van Voorbeeldministerie op de offerte. Jij hoeft nu niets te doen.',
  needs_me: false,
  action_text: null,
  waits_on: 'Voorbeeldministerie',
  work_href: '/opdrachten/a-2/offerte',
  status: 'waiting',
  status_label: 'Wacht op een ander',
  waiting_on: 'de opdrachtgever',
  track_label: 'Offerte',
  case_label: 'Opdracht Beta 2026',
  assignment_id: 'a-2',
  assignment_name: 'Opdracht Beta 2026',
});
/** A task of someone else on a case I started: I wait for it. */
const AWAITED = task({
  id: 't-awaited',
  title: 'Vul de rol Ontwerper in',
  headline: 'De invulling van de rol Ontwerper',
  instruction: 'Je wacht op een planner, die de rol Ontwerper invult. Jij hoeft nu niets te doen.',
  is_mine: false,
  needs_me: false,
  action_text: null,
  waits_on: 'een planner',
  work_href: '/opdrachten/a-1/bemensing',
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

describe('telling', () => {
  it('splits what I must do from what I wait for, the soonest first', () => {
    const work = myWork([SOON, WAITING, LATE], [AWAITED]);
    expect(work.toDo).toEqual([LATE, SOON]);
    expect(work.waiting.map((item) => item.id).sort()).toEqual(['t-awaited', 't-wait']);
  });

  it('sends who must do a task to the place of the work, with the task in the address', () => {
    expect(goesToWork(LATE)).toBe(true);
    expect(workHref(LATE)).toBe('/opdrachten/a-1/maandafsluiting?maand=2026-09&bij-taak=t-late');
    expect(workHref(AWAITED)).toBe('/opdrachten/a-1/bemensing?bij-taak=t-awaited');
    // Who waits reads the task; a task of your own is finished where it is read.
    expect(goesToWork(WAITING)).toBe(false);
    expect(goesToWork({ ...MANUAL, needs_me: true, is_mine: true })).toBe(false);
  });

  it('names what a task is about and by when', () => {
    expect(aboutLine(LATE)).toBe('Opdracht Alfa 2026');
    expect(
      aboutLine(task({ case_kind: 'vacancy', vacancy_id: 'v-1', vacancy_title: 'Developer' })),
    ).toBe('Vacature Developer · Opdracht Alfa 2026');
    expect(dueWords(LATE)).toBe('Te laat: vóór 7 okt 2026');
    expect(dueWords(task({ due_on: null }))).toBe('');
  });
});

describe('grouping', () => {
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
  it('cannot be ticked when a fact closes it', () => {
    expect(movesOf(LATE).map((move) => move.text)).toEqual(['Begin', 'Wacht op een ander']);
  });

  it('can be ticked when it is a task of your own', () => {
    expect(movesOf(MANUAL).map((move) => move.text)).toContain('Rond af');
  });

  it('offers nothing to a reader who may not change it', () => {
    expect(movesOf({ ...MANUAL, can_change: false })).toEqual([]);
  });
});

describe('TasksPage', () => {
  it('shows what I must do apart from what I wait for', async () => {
    stubApi({ '/api/tasks/mine': { items: [SOON, LATE, WAITING], awaited: [AWAITED] } });
    const { container } = renderApp(<TasksPage />, { path: '/taken' });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Taken');
    await waitFor(() => expect(container.querySelectorAll('nldd-table')).toHaveLength(2));
    const headings = [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
      el.getAttribute('text'),
    );
    expect(headings).toEqual(['Te doen', 'Wacht op anderen']);
    const [toDo, waiting] = [...container.querySelectorAll('nldd-table')];
    // The late one first; each task by what to do, and on what.
    const names = (table: Element | undefined) =>
      [...(table?.querySelectorAll('nldd-table-row:not([slot]) nldd-link') ?? [])].map((el) =>
        el.getAttribute('text'),
      );
    expect(names(toDo)).toEqual(['Sluit september 2026 af', 'Vul de rol Ontwerper in']);
    expect(names(waiting).sort()).toEqual([
      'Akkoord van de opdrachtgever',
      'De invulling van de rol Ontwerper',
    ]);
    expect(waiting).toHaveTextContent('Wacht op Voorbeeldministerie · Opdracht Beta 2026');
    expect(waiting).toHaveTextContent('Wacht op een planner');
    // Nothing is open by default, and no word about how tasks close.
    expect(container.ownerDocument.querySelector('nldd-sheet[open]')).toBeNull();
    expect(container).not.toHaveTextContent('Sluit vanzelf');
  });

  it('leads who approves quotes to the quotes that wait, and nobody else', async () => {
    stubApi({ '/api/tasks/mine': { items: [SOON], awaited: [] } });
    const plain = renderApp(<TasksPage />, { path: '/taken' });
    await waitFor(() => expect(plain.container.querySelector('nldd-table')).not.toBeNull());
    expect(plain.container.querySelector('[text="Offertes ter goedkeuring"]')).toBeNull();
    plain.unmount();

    const approver = renderApp(<TasksPage />, {
      path: '/taken',
      auth: {
        status: 'authenticated',
        person: TEST_PERSON,
        functions: ['offertegoedkeurder'],
      },
    });
    await waitFor(() => expect(approver.container.querySelector('nldd-table')).not.toBeNull());
    expect(
      approver.container.querySelector('[text="Offertes ter goedkeuring"]')?.getAttribute('href'),
    ).toBe('/goedkeuren');
  });

  it('says so when there is nothing to do', async () => {
    stubApi({ '/api/tasks/mine': {} });
    const { container } = renderApp(<TasksPage />, { path: '/taken' });
    await waitFor(() => expect(container.querySelector('[text="Niets te doen"]')).not.toBeNull());
  });

  it('draws the board in four columns, each task in the words for this reader', async () => {
    stubApi({ '/api/tasks': { items: [LATE, MANUAL, WAITING] } });
    const { container } = renderApp(<TasksPage />, { path: '/taken?weergave=bord' });
    await waitFor(() => expect(container.querySelectorAll('nldd-card')).toHaveLength(3));
    const columns = [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
      el.getAttribute('text'),
    );
    expect(columns).toEqual(['Te doen (2)', 'Bezig (0)', 'Wacht op een ander (1)', 'Klaar (0)']);
    expect(container).not.toHaveTextContent('Sluit vanzelf');
    expect(container).toHaveTextContent('wacht op Voorbeeldministerie');
    expect(container).toHaveTextContent('Voor jou');
    // Every card opens by a link.
    const link = container.querySelector('nldd-card nldd-link');
    expect(link).toHaveAttribute('href', '/taken?weergave=bord&taak=t-late');
    // And moves by a menu: no dragging needed.
    expect(container.querySelectorAll('nldd-card nldd-menu')).toHaveLength(3);
  });

  it('tells a task I must do: what, why, by when, and one button that leads to the work', async () => {
    stubApi({
      '/api/tasks/mine': { items: [LATE] },
      '/api/tasks/t-late': {
        ...LATE,
        notes: [
          {
            id: 'n-1',
            body: 'Uren nog niet compleet.',
            created_at: '2026-10-08T09:00:00Z',
            author_name: 'Fictieve Collega',
          },
        ],
      },
    });
    renderApp(<TasksPage />, { path: '/taken?taak=t-late' });
    await waitFor(() => expect(document.body).toHaveTextContent('Uren nog niet compleet.'));
    const sheet = document.querySelector('nldd-sheet');
    expect(sheet).toHaveAttribute('open');
    expect(sheet).toHaveTextContent('Stel vast wie in september 2026 hoeveel heeft gewerkt');
    expect(sheet).not.toHaveTextContent('Sluit vanzelf');
    // One primary button, named after the work; the note is not it.
    const primary = [...(sheet?.querySelectorAll('nldd-button[appearance="primary"]') ?? [])];
    expect(primary.map((el) => el.getAttribute('text'))).toEqual(['Sluit september 2026 af']);
    expect(sheet?.querySelector('nldd-button[text="Bewaar notitie"]')).toBeNull();
    expect(sheet?.querySelector('nldd-button[text="Schrijf een notitie"]')).not.toBeNull();
    // What it is about is a link to the thing itself.
    expect(sheet?.querySelector('nldd-link[href="/opdrachten/a-1"]')).toHaveAttribute(
      'text',
      'Opdracht Alfa 2026',
    );
    const labels = [
      ...(sheet?.querySelectorAll('nldd-list-item nldd-text-cell[color="secondary"]') ?? []),
    ];
    expect(labels.map((el) => el.getAttribute('text'))).toEqual([
      'Waarover',
      'Waarom nu',
      'Vóór',
      'Vervolg',
    ]);
  });

  it('gives who waits no button, and says who is waited on', async () => {
    stubApi({ '/api/tasks/mine': { items: [WAITING] }, '/api/tasks/t-wait': WAITING });
    renderApp(<TasksPage />, { path: '/taken?taak=t-wait' });
    const sheet = () => document.querySelector('nldd-sheet');
    await waitFor(() => expect(sheet()).toHaveTextContent('Je wacht op het akkoord van'));
    expect(sheet()?.querySelector('nldd-button[appearance="primary"]')).toBeNull();
    expect(
      sheet()?.querySelector('nldd-link[text="Ga naar de plek van het werk"]'),
    ).toHaveAttribute('href', '/opdrachten/a-2/offerte?bij-taak=t-wait');
  });

  it('says why nobody can do a task and who can change that', async () => {
    const blocked = {
      ...AWAITED,
      blocked: 'Niemand heeft het recht Planner in grip. Een beheerder geeft dat recht bij Team.',
    };
    stubApi({ '/api/tasks/mine': { awaited: [blocked] }, '/api/tasks/t-awaited': blocked });
    renderApp(<TasksPage />, { path: '/taken?taak=t-awaited' });
    await waitFor(() =>
      expect(document.querySelector('nldd-sheet nldd-banner[variant="warning"]')).toHaveAttribute(
        'text',
        blocked.blocked,
      ),
    );
  });

  it('lists what a request still misses', async () => {
    const request = task({
      id: 't-req',
      headline: 'Vraag de vacature aan',
      action_text: 'Bereid aanvraag voor',
      work_href: '/vacatures/v-1',
      checklist: [
        { text: 'Schaal' },
        { text: 'Soort contract' },
        { text: 'Functienaam', done: true },
      ],
    });
    stubApi({ '/api/tasks/mine': { items: [request] }, '/api/tasks/t-req': request });
    renderApp(<TasksPage />, { path: '/taken?taak=t-req' });
    await waitFor(() =>
      expect(document.querySelector('nldd-sheet')).toHaveTextContent(
        'Ontbreekt nog: schaal, soort contract.',
      ),
    );
  });
});

describe('the Taken tab of a case', () => {
  const CASE: CaseTasksData = {
    case_kind: 'assignment',
    case_id: 'a-1',
    plan_version: '2026.1',
    can_add: true,
    tracks: [
      {
        key: 'offerte',
        label: 'Offerte',
        open_count: 0,
        waiting_count: 0,
        standing: 'Niets te doen',
        tasks: [],
      },
      {
        key: 'uitvoering',
        label: 'Uitvoering',
        open_count: 1,
        waiting_count: 0,
        standing: LATE.title,
        tasks: [LATE],
      },
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

  it('shows the tasks per track, once', async () => {
    const { container } = renderTab(CASE);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    // The tasks themselves say where each track stands; no summary repeats them.
    expect(container.querySelector('nldd-list[accessible-label="Stand per spoor"]')).toBeNull();
    expect(container.querySelectorAll('nldd-table')).toHaveLength(1);
    expect(container.querySelector('nldd-button[text="Nieuwe taak"]')).not.toBeNull();
  });

  it('offers no new task to a reader who may only read', async () => {
    const { container } = renderTab({ ...CASE, can_add: false });
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-button[text="Nieuwe taak"]')).toBeNull();
  });
});

describe('the Taken tab when the API fails', () => {
  it('shows one calm notice and no table', async () => {
    stubApi({});
    const { container } = renderApp(
      <Routes>
        <Route path="/opdrachten/:assignmentId/taken" element={<AssignmentTasksTab />} />
      </Routes>,
      { path: '/opdrachten/a-1/taken' },
    );
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog, nldd-banner')).not.toBeNull(),
    );
    expect(container.querySelector('nldd-table')).toBeNull();
    expect(container.querySelector('nldd-button[text="Nieuwe taak"]')).toBeNull();
  });
});

describe('MyTasksBlock', () => {
  it('shows what I must do first, each as a link to its work, and a link to the rest', async () => {
    const third = task({
      id: 't-3',
      title: 'Bied de offerte aan',
      work_href: '/opdrachten/a-1/offerte',
    });
    stubApi({ '/api/tasks/mine': { items: [SOON, WAITING, third, LATE] } });
    const { container } = renderApp(<MyTasksBlock limit={2} />);
    await waitFor(() => expect(container.querySelectorAll('nldd-link')).toHaveLength(3));
    const links = [...container.querySelectorAll('nldd-link')];
    // What waits on someone else is not on the start page.
    expect(links.map((link) => link.getAttribute('text'))).toEqual([
      LATE.title,
      SOON.title,
      'Alle taken (3)',
    ]);
    expect(links[0]).toHaveAttribute(
      'href',
      '/opdrachten/a-1/maandafsluiting?maand=2026-09&bij-taak=t-late',
    );
    expect(links[2]).toHaveAttribute('href', '/taken');
    expect(container).toHaveTextContent('Opdracht Alfa 2026 · Te laat: vóór 7 okt 2026');
  });

  it('is calm when there is nothing, and when the API fails', async () => {
    stubApi({ '/api/tasks/mine': {} });
    const empty = renderApp(<MyTasksBlock />);
    await waitFor(() => expect(empty.container).toHaveTextContent('Niets te doen'));
    empty.unmount();
    stubApi({});
    const failed = renderApp(<MyTasksBlock />);
    await waitFor(() =>
      expect(failed.container).toHaveTextContent('De taken zijn nu niet te laden.'),
    );
  });
});

describe('TaskBar', () => {
  function renderBar(path: string) {
    return renderApp(
      <Routes>
        <Route path="*" element={<TaskBar />} />
      </Routes>,
      { path },
    );
  }

  it('says on the page of the work which task the reader came to do', async () => {
    stubApi({ '/api/tasks/t-late': LATE });
    const { container } = renderBar(
      '/opdrachten/a-1/maandafsluiting?maand=2026-09&bij-taak=t-late',
    );
    await waitFor(() => expect(container.querySelector('nldd-banner')).not.toBeNull());
    const bar = container.querySelector('nldd-banner');
    expect(bar).toHaveAttribute('text', 'Taak: Sluit september 2026 af');
    expect(bar?.getAttribute('supporting-text')).toContain('Stel vast wie in september 2026');
    expect(bar?.getAttribute('supporting-text')).toContain('Te laat: vóór 7 okt 2026.');
    expect(bar?.querySelector('nldd-button')).toHaveAttribute('href', '/taken');
  });

  it('says so when the work is done', async () => {
    stubApi({ '/api/tasks/t-late': { ...LATE, status: 'done' } });
    const { container } = renderBar('/opdrachten/a-1/maandafsluiting?bij-taak=t-late');
    await waitFor(() =>
      expect(container.querySelector('nldd-banner')).toHaveAttribute(
        'text',
        'Gedaan: Sluit september 2026 af',
      ),
    );
    expect(container.querySelector('nldd-banner')).toHaveAttribute('variant', 'success');
  });

  it('draws nothing on a page that was not opened for a task', () => {
    stubApi({});
    const { container } = renderBar('/opdrachten/a-1/maandafsluiting');
    expect(container.querySelector('nldd-banner')).toBeNull();
  });
});

describe('the navigation', () => {
  it('counts what I must do, not what waits on others', async () => {
    stubApi({ '/api/tasks/count': { open: 3, to_do: 2, overdue: 1 } });
    const { container } = renderApp(<MainNavigation />, { path: '/' });
    const item = () => container.querySelector('nldd-menu-bar-item[href="/taken"]');
    await waitFor(() => expect(item()?.querySelector('nldd-badge')).toHaveAttribute('number', '2'));
    expect(item()).toHaveAttribute('text', 'Taken');
    expect(item()).toHaveAttribute('accessible-label', 'Taken, 2 taken te doen');
  });

  it('shows the plain word when there is nothing', async () => {
    stubApi({ '/api/tasks/count': {} });
    const { container } = renderApp(<MainNavigation />, { path: '/' });
    const item = container.querySelector('nldd-menu-bar-item[href="/taken"]');
    expect(item).toHaveAttribute('text', 'Taken');
    expect(item?.querySelector('nldd-badge')).toBeNull();
    expect(item).not.toHaveAttribute('accessible-label');
  });
});
