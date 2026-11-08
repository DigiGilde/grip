import { fireEvent, screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { renderApp } from '@/test/utils';
import type { TextVersion, Vacancy, VacancyHire, VacancyOptions } from './api';
import { VACANCY_PART_SEGMENTS } from './paths';
import { DecisionsPart } from './parts/DecisionsPart';
import { DetailsPart } from './parts/DetailsPart';
import { FulfilmentPart } from './parts/FulfilmentPart';
import { RequestPart } from './parts/RequestPart';
import { TasksPart } from './parts/TasksPart';
import { TextPart } from './parts/TextPart';
import type { VacancyPart } from './partsApi';
import { VacancyLanding } from './VacancyLanding';
import { VacancyLayout } from './VacancyLayout';

const OPTIONS: VacancyOptions = {
  vacancy_types: [{ value: 'regulier', label: 'Regulier' }],
  contract_types: [{ value: 'temporary_project', label: 'Tijdelijk (projectcontract)' }],
  statuses: [],
  channels: [{ value: 'internal', label: 'Intern' }],
  decision_kinds: [],
  text_kinds: [],
  steps: [],
  drafting_available: false,
  request_form_available: false,
  can_create_without_budget_line: false,
  can_manage_setup: false,
};

const NO_PERMISSIONS = {
  can_edit: false,
  can_record_hr_advice: false,
  can_record_control_advice: false,
  can_record_approval: false,
  can_download_form: false,
};

const MODEL_DRAFT: TextVersion = {
  id: 't-2',
  kind: 'vacancy_text',
  body: 'Concept van het model.',
  source: 'model',
  model_id: 'testmodel-1',
  prompt_version: 'v1',
  created_at: '2026-10-02T09:00:00Z',
  model_assisted: true,
  origin_model_id: 'testmodel-1',
  origin_drafted_at: '2026-10-02T09:00:00Z',
  is_current: false,
};

const OLDER: TextVersion = {
  id: 't-1',
  kind: 'vacancy_text',
  body: 'Eerdere versie.',
  source: 'human',
  created_at: '2026-10-01T09:00:00Z',
  model_assisted: false,
  is_current: false,
};

const REQUESTED: Vacancy = {
  id: 'v-1',
  function_title: 'Backend-ontwikkelaar',
  scale: 11,
  fte: '0.80',
  status: 'requested',
  declarable: true,
  vacancy_type: 'regulier',
  contract_type: 'temporary_project',
  channels: [],
  budget_line_id: 'b-1',
  assignment_id: 'a-1',
  assignment_name: 'Opdracht Alfa',
  requested_on: '2026-09-28',
  has_openings: true,
  procedure: [
    {
      kind: 'request',
      label: 'Aanvraag',
      position: 1,
      recorded: true,
      started_on: '2026-09-28',
      ended_on: '2026-09-28',
    },
    {
      kind: 'internal_opening',
      label: 'Interne openstelling',
      position: 5,
      recorded: false,
      minimum_working_days: 5,
    },
  ],
  decisions: [
    {
      kind: 'hr_advice',
      label: 'Advies HR',
      person_name: 'Fictieve Adviseur',
      has_account: true,
    },
  ],
  texts: [OLDER, MODEL_DRAFT],
  requester_name: 'Fictieve Eigenaar',
  addressee_name: 'Fictief Directielid',
  addressee_has_account: false,
  permissions: { ...NO_PERMISSIONS, can_edit: true, can_download_form: true },
};

const PUBLIC: Vacancy = {
  id: 'v-2',
  function_title: 'Productmanager',
  scale: 13,
  fte: '1.00',
  status: 'open',
  published_at: '2026-10-05T08:00:00Z',
  published_text: {
    body: 'Wij zoeken een productmanager.',
    established_at: '2026-10-02T08:00:00Z',
    model_assisted: true,
    model_id: 'testmodel-1',
    drafted_at: '2026-10-01T08:00:00Z',
  },
  procedure: [],
  decisions: [],
  texts: [],
  permissions: NO_PERMISSIONS,
};

const HIRE: VacancyHire = {
  vacancy_id: 'v-1',
  recruitment_ref: {
    system: 'emply',
    reference: 'V-2026-014',
    url: 'https://werving.example/v/14',
  },
  hire: {
    person_id: 'p-7',
    person_name: 'Fictieve Collega',
    start_date: '2027-01-04',
    stage: 'prospective',
  },
};

/** Answers GET requests from a table of path to body; anything else is a 404. */
function stubApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split('?')[0] ?? '';
      if (path in routes) {
        return new Response(JSON.stringify(routes[path]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(
        JSON.stringify({
          type: 'about:blank',
          title: 'Niet gevonden',
          status: 404,
        }),
        {
          status: 404,
          headers: { 'Content-Type': 'application/problem+json' },
        },
      );
    }),
  );
}

const part = (
  key: VacancyPart['key'],
  label: string,
  state: VacancyPart['state'] = null,
  notice: string | null = null,
): VacancyPart => ({ key, label, state, notice });

const REQUEST = part('request', 'Aanvraag', 'done');
const DECISIONS = part('decisions', 'Advies en akkoord', 'waiting', 'Wacht op Fictief Directielid');
const TEXT = part('text', 'Tekst en openstellen', 'future');
const FULFILMENT = part('fulfilment', 'Vervullen', 'future');
const DETAILS = part('details', 'Gegevens');
const HISTORY = part('history', 'Geschiedenis');
const ALL_PARTS = [REQUEST, DECISIONS, TEXT, FULFILMENT, DETAILS, HISTORY];

const partsAre = (parts: VacancyPart[], tasksLink = true, id = 'v-1') => ({
  [`/api/vacancies/${id}/parts`]: { vacancy_id: id, parts, tasks_link: tasksLink },
});

function renderVacancy(vacancy: Vacancy, tab = 'aanvraag', extra: Record<string, unknown> = {}) {
  stubApi({
    [`/api/vacancies/${vacancy.id}`]: vacancy,
    ...partsAre(ALL_PARTS, true, vacancy.id),
    '/api/vacancies/options': OPTIONS,
    [`/api/vacancies/${vacancy.id}/request-forms`]: {
      available: true,
      may_make: true,
      current: null,
      earlier: [],
      changed: [],
      signed: [],
    },
    [`/api/vacancies/${vacancy.id}/request-form/status`]: {
      available: true,
      file_name: 'formulier.pdf',
      open_fields: [],
      motivation_established: false,
    },
    ...extra,
  });
  return renderApp(
    <Routes>
      <Route path={PATHS.vacancyDetail} element={<VacancyLayout />}>
        <Route index element={<VacancyLanding />} />
        <Route path={VACANCY_PART_SEGMENTS.request} element={<RequestPart />} />
        <Route path={VACANCY_PART_SEGMENTS.decisions} element={<DecisionsPart />} />
        <Route path={VACANCY_PART_SEGMENTS.text} element={<TextPart />} />
        <Route path={VACANCY_PART_SEGMENTS.fulfilment} element={<FulfilmentPart />} />
        <Route path={VACANCY_PART_SEGMENTS.details} element={<DetailsPart />} />
        <Route path={VACANCY_PART_SEGMENTS.tasks} element={<TasksPart />} />
      </Route>
    </Routes>,
    { path: `/vacatures/${vacancy.id}${tab ? `/${tab}` : ''}` },
  );
}

const STEPS = ['Aanvraag', 'Advies en akkoord', 'Openstellen', 'Vervullen'];

/**
 * The course of the vacancy as the server would give it: which step it is
 * at and what is next for this reader. The shell only draws it.
 */
function courseAt(current: number, next: Record<string, unknown> | null) {
  return {
    '/api/tasks/cases/vacancy/v-1/course': {
      case_kind: 'vacancy',
      case_id: 'v-1',
      course: {
        key: 'werving',
        label: 'Werving',
        steps: STEPS.map((label, index) => ({
          key: label,
          label,
          state: index + 1 < current ? 'done' : index + 1 === current ? 'current' : 'future',
        })),
        current_label: STEPS[current - 1],
        position: `${current} van ${STEPS.length}`,
        next,
      },
      parts: [],
    },
  };
}

const primaryOnPage = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-button[appearance="primary"]')].map((button) =>
    button.getAttribute('text'),
  );

const tabsOf = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-menu-bar-item')].map((tab) => [
    tab.getAttribute('text'),
    tab.hasAttribute('current'),
  ]);

afterEach(() => {
  vi.unstubAllGlobals();
});

const rowsOf = (container: HTMLElement, label: string) =>
  [...container.querySelectorAll(`nldd-list[accessible-label="${label}"] nldd-list-item`)].map(
    (row) => {
      const cell = row.querySelector('nldd-text-cell');
      return [
        cell?.getAttribute('text'),
        cell?.getAttribute('supporting-text') ?? null,
        row.querySelector('nldd-badge')?.getAttribute('text') ?? null,
      ];
    },
  );

describe('the landing of a vacancy', () => {
  const STEPS_LABEL = 'Stappen van de vacature Backend-ontwikkelaar';
  const ABOUT_LABEL = 'Over de vacature Backend-ontwikkelaar';

  it('has the steps as rows with their stand, as the server gives them, and no step bar', async () => {
    const { container } = renderVacancy(REQUESTED, '', {
      ...partsAre([
        REQUEST,
        DECISIONS,
        part('text', 'Tekst en openstellen', 'current', 'Leg de link naar de vacature vast'),
        part('fulfilment', 'Vervullen', 'current', 'Leg vast wie is aangenomen'),
        DETAILS,
        HISTORY,
      ]),
    });
    await waitFor(() => expect(rowsOf(container, STEPS_LABEL)).toHaveLength(4));
    expect(rowsOf(container, STEPS_LABEL)).toEqual([
      ['Aanvraag', null, 'Klaar'],
      ['Advies en akkoord', 'Wacht op Fictief Directielid', null],
      ['Tekst en openstellen', 'Jij: leg de link naar de vacature vast', 'Nu aan de beurt'],
      ['Vervullen', 'Jij: leg vast wie is aangenomen', 'Nu aan de beurt'],
    ]);
    expect(rowsOf(container, ABOUT_LABEL).map(([text]) => text)).toEqual([
      'Gegevens',
      'Geschiedenis',
    ]);
    expect(
      container.querySelector(`nldd-list[accessible-label="${STEPS_LABEL}"] nldd-list-item`),
    ).toHaveAttribute('href', '/vacatures/v-1/aanvraag');
    expect(container.querySelector('nldd-step-bar')).toBeNull();
    expect(container.querySelector('[aria-label^="Verloop van"]')).toBeNull();
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
  });

  it('follows the answer: a row the server leaves out is not there', async () => {
    const { container } = renderVacancy(
      { ...REQUESTED, permissions: NO_PERMISSIONS },
      '',
      partsAre([REQUEST, DECISIONS, part('text', 'Tekst'), HISTORY]),
    );
    await waitFor(() => expect(rowsOf(container, STEPS_LABEL)).toHaveLength(3));
    expect(rowsOf(container, STEPS_LABEL).map(([text]) => text)).toEqual([
      'Aanvraag',
      'Advies en akkoord',
      'Tekst',
    ]);
    expect(rowsOf(container, ABOUT_LABEL).map(([text]) => text)).toEqual(['Geschiedenis']);
  });

  it('says what it is, where it belongs and what happens now', async () => {
    const { container } = renderVacancy(
      REQUESTED,
      '',
      courseAt(2, {
        mine: false,
        headline: 'Het advies van HR',
        sentence: 'Je wacht op het advies van HR. Jij hoeft nu niets te doen.',
        who: 'HR',
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Backend-ontwikkelaar'),
    );
    await waitFor(() => expect(container.textContent).toContain('Je wacht op het advies van HR.'));
    expect(document.title).toContain('Backend-ontwikkelaar');
    expect(container.querySelector('nldd-title')?.getAttribute('supporting-text')).toBe(
      'Vacature bij Opdracht Alfa, schaal 11, 0,8 fte',
    );
    expect(container.querySelector('nldd-badge[text="Aangevraagd"]')).toBeNull();
    // Someone else has the move: nothing on the page takes the accent.
    expect(primaryOnPage(container)).toEqual([]);
    expect(container.querySelectorAll('h1')).toHaveLength(1);
    expect(
      container.querySelector('nldd-link[text="Alle taken van deze vacature"]'),
    ).toHaveAttribute('href', '/vacatures/v-1/taken');
  });

  it('keeps kind and period in the lead for a reader without the row Gegevens', async () => {
    const dated: Vacancy = { ...REQUESTED, start_date: '2026-07-01', end_date: '2027-06-30' };
    const without = renderVacancy(dated, '', partsAre([REQUEST, HISTORY]));
    await waitFor(() => expect(rowsOf(without.container, ABOUT_LABEL)).toHaveLength(1));
    expect(without.container.querySelector('nldd-title')?.getAttribute('supporting-text')).toBe(
      'Vacature bij Opdracht Alfa, schaal 11, 0,8 fte, regulier, 1 jul 2026 t/m 30 jun 2027',
    );
    without.unmount();
    const { container } = renderVacancy(dated, '');
    await waitFor(() => expect(rowsOf(container, ABOUT_LABEL)).toHaveLength(2));
    expect(container.querySelector('nldd-title')?.getAttribute('supporting-text')).toBe(
      'Vacature bij Opdracht Alfa, schaal 11, 0,8 fte',
    );
    expect(rowsOf(container, ABOUT_LABEL)[0]?.[1]).toBe('Regulier, 1 jul 2026 t/m 30 jun 2027');
  });

  it('has no link to the tasks when the server says there is none for this reader', async () => {
    const { container } = renderVacancy(REQUESTED, '', partsAre(ALL_PARTS, false));
    await waitFor(() => expect(rowsOf(container, STEPS_LABEL)).toHaveLength(4));
    expect(container.querySelector('nldd-link[text="Alle taken van deze vacature"]')).toBeNull();
  });

  it('links the tasks from the line about more to do, and not twice', async () => {
    const withMore = courseAt(2, {
      mine: true,
      headline: 'Het advies van HR',
      sentence: 'Geef je advies.',
      action_text: 'Geef advies',
      action_href: '/vacatures/v-1/advies',
      task_key: 'werving.advies_hr',
    });
    const key = '/api/tasks/cases/vacancy/v-1/course';
    Object.assign(withMore[key].course, { more_to_do: 2 });
    const { container } = renderVacancy(REQUESTED, '', withMore);
    await waitFor(() =>
      expect(container.querySelector('nldd-link[text="En nog 2 taken voor jou"]')).toHaveAttribute(
        'href',
        '/vacatures/v-1/taken',
      ),
    );
    expect(container.querySelector('nldd-link[text="Alle taken van deze vacature"]')).toBeNull();
  });

  it('carries the next step that is done in a sheet as its one primary button', async () => {
    const { container } = renderVacancy(
      REQUESTED,
      '',
      courseAt(4, {
        mine: true,
        headline: 'Leg vast wie is aangenomen',
        sentence: 'De vacature kan worden vervuld.',
        action_text: 'Vervul',
        action_href: '/vacatures/v-1/vervulling',
        task_key: 'werving.vervullen',
      }),
    );
    await waitFor(() => expect(primaryOnPage(container)).toEqual(['Vervul']));
  });

  it('offers no step that leads to a part the reader does not have', async () => {
    const { container } = renderVacancy(REQUESTED, '', {
      ...partsAre([REQUEST, DECISIONS, TEXT, DETAILS, HISTORY]),
      ...courseAt(4, {
        mine: true,
        headline: 'Leg vast wie is aangenomen',
        sentence: 'De vacature kan worden vervuld.',
        action_text: 'Bekijk de vervulling',
        action_href: '/vacatures/v-1/vervulling',
        task_key: 'werving.collega_voorstellen',
      }),
    });
    await waitFor(() => expect(container.textContent).toContain('De vacature kan worden vervuld.'));
    expect(primaryOnPage(container)).toEqual([]);
  });

  it('says how it ended, once it has ended', async () => {
    const withdrawn: Vacancy = { ...REQUESTED, status: 'withdrawn' };
    const { container } = renderVacancy(withdrawn, '', {
      ...partsAre([REQUEST, HISTORY]),
      '/api/tasks/cases/vacancy/v-1/course': {
        case_kind: 'vacancy',
        case_id: 'v-1',
        course: { key: 'werving', label: 'Werving', steps: [], ended: 'Ingetrokken' },
        parts: [],
      },
    });
    await waitFor(() =>
      expect(container.querySelector('nldd-badge[text="Ingetrokken"]')).not.toBeNull(),
    );
  });

  it('says so when the vacancy is not there or not visible', async () => {
    stubApi({ '/api/vacancies/options': OPTIONS });
    const { container } = renderApp(
      <Routes>
        <Route path={PATHS.vacancyDetail} element={<VacancyLayout />} />
      </Routes>,
      { path: '/vacatures/v-9' },
    );
    await waitFor(() =>
      expect(container.querySelector('[data-state="not-found"]')?.textContent).toContain(
        'Deze vacature is niet gevonden',
      ),
    );
  });
});

describe('a reader of only the published text', () => {
  it('sees that text and nothing to do', async () => {
    const { container } = renderVacancy(PUBLIC, '');
    await waitFor(() => expect(container.textContent).toContain('Wij zoeken een productmanager.'));
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Productmanager');
    expect(container.textContent).toContain('Een taalmodel (testmodel-1)');
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
    expect(container.querySelector('nldd-list')).toBeNull();
    expect(container.querySelector('nldd-button')).toBeNull();
    expect(document.body.querySelector('nldd-sheet')).toBeNull();
    const asked = vi.mocked(fetch).mock.calls.map(([input]) => String(input));
    expect(asked.some((url) => url.includes('/parts'))).toBe(false);
    expect(asked.some((url) => url.includes('/course'))).toBe(false);
  });

  it.each(['aanvraag', 'tekst', 'vervulling', 'taken'])('has no part at /%s', async (segment) => {
    const { container } = renderVacancy(PUBLIC, segment);
    await waitFor(() => expect(container.querySelector('[data-state="no-access"]')).not.toBeNull());
    expect(container.textContent).not.toContain('Wij zoeken een productmanager.');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Productmanager');
  });
});

describe('a part of a vacancy', () => {
  it('is a page with its name, the way back and the bar to the other parts', async () => {
    const { container } = renderVacancy(REQUESTED, 'advies');
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Advies en akkoord'),
    );
    expect(document.title).toContain('Advies en akkoord, Backend-ontwikkelaar');
    expect(
      container.querySelector('nldd-link[text="Terug naar Backend-ontwikkelaar"]'),
    ).toHaveAttribute('href', '/vacatures/v-1');
    expect(tabsOf(container)).toEqual([
      ['Aanvraag', false],
      ['Advies en akkoord', true],
      ['Tekst en openstellen', false],
      ['Vervullen', false],
      ['Gegevens', false],
      ['Geschiedenis', false],
    ]);
  });

  it('has no bar to the other parts on a narrow screen', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation(() => ({
        matches: true,
        addEventListener: () => {},
        removeEventListener: () => {},
      })),
    );
    const { container } = renderVacancy(REQUESTED, 'advies');
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Advies en akkoord'),
    );
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
  });

  it('says there is no access when the server gives the reader no such row', async () => {
    const { container } = renderVacancy(
      REQUESTED,
      'vervulling',
      partsAre([REQUEST, DECISIONS, TEXT, DETAILS, HISTORY]),
    );
    await waitFor(() => expect(container.querySelector('[data-state="no-access"]')).not.toBeNull());
    expect(container.querySelector('nldd-button[text="Leg verwijzing vast"]')).toBeNull();
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
  });

  it('has the tasks only when the server gives the link', async () => {
    const { container } = renderVacancy(REQUESTED, 'taken', partsAre(ALL_PARTS, false));
    await waitFor(() => expect(container.querySelector('[data-state="no-access"]')).not.toBeNull());
  });

  it('carries the step that is done in a sheet here, and steps its own button back', async () => {
    const approved: Vacancy = { ...REQUESTED, status: 'approved' };
    const { container } = renderVacancy(
      approved,
      'tekst',
      courseAt(3, {
        mine: true,
        headline: 'Stel de vacature open',
        sentence: 'Het akkoord is gegeven. Stel de vacature open.',
        action_text: 'Stel open',
        action_href: '/vacatures/v-1/tekst',
        task_key: 'werving.openstellen',
      }),
    );
    await waitFor(() =>
      expect(
        container.querySelector('nldd-table[accessible-label="Stappen van de procedure"]'),
      ).not.toBeNull(),
    );
    await waitFor(() => expect(primaryOnPage(container)).toEqual(['Stel open']));
    expect(container.querySelectorAll('nldd-button[text="Stel open"]')).toHaveLength(1);
  });

  it('does not carry a step that is done on another part', async () => {
    const { container } = renderVacancy(
      REQUESTED,
      'gegevens',
      courseAt(3, {
        mine: true,
        headline: 'Stel de vacature open',
        sentence: 'Het akkoord is gegeven. Stel de vacature open.',
        action_text: 'Stel open',
        action_href: '/vacatures/v-1/tekst',
        task_key: 'werving.openstellen',
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Gegevens'),
    );
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/course'))).toBe(
        true,
      ),
    );
    await new Promise((resolve) => setTimeout(resolve));
    expect(primaryOnPage(container)).toEqual([]);
  });
});

describe('one way to change the request', () => {
  const PREPARE = courseAt(1, {
    mine: true,
    headline: 'Maak de aanvraag compleet',
    sentence: 'De aanvraag mist nog gegevens.',
    action_text: 'Bereid aanvraag voor',
    action_href: '/vacatures/v-1/aanvraag',
    missing: ['Functienaam uit het functiegebouw', 'Soort contract'],
    task_key: 'werving.aanvraag_voorbereiden',
  });
  const DRAFT: Vacancy = { ...REQUESTED, status: 'draft', contract_type: null };
  const editOn = (container: HTMLElement) =>
    container.querySelector('nldd-button[text="Wijzig functie, fte of periode"]');

  it('is the button on the landing, with what is missing', async () => {
    const { container } = renderVacancy(DRAFT, '', PREPARE);
    await waitFor(() => expect(primaryOnPage(container)).toEqual(['Bereid aanvraag voor']));
    expect(container.textContent).toContain(
      'Ontbreekt nog: Functienaam uit het functiegebouw, Soort contract.',
    );
    expect(editOn(container)).toBeNull();
  });

  it('is the rows on the request, without that button above them', async () => {
    const { container } = renderVacancy(DRAFT, 'aanvraag', PREPARE);
    await waitFor(() => expect(container.querySelector('nldd-list-item[button]')).not.toBeNull());
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/course'))).toBe(
        true,
      ),
    );
    await new Promise((resolve) => setTimeout(resolve));
    expect(primaryOnPage(container)).toEqual([]);
    expect(container.querySelector('nldd-button[text="Bereid aanvraag voor"]')).toBeNull();
    expect(editOn(container)).toBeNull();
  });

  it('keeps the request itself as the button on the request', async () => {
    const { container } = renderVacancy(
      DRAFT,
      'aanvraag',
      courseAt(1, {
        mine: true,
        headline: 'Vraag de vacature aan',
        sentence: 'De aanvraag is compleet.',
        action_text: 'Vraag aan',
        action_href: '/vacatures/v-1/aanvraag',
        missing: [],
        task_key: 'werving.aanvraag_voorbereiden',
      }),
    );
    await waitFor(() => expect(primaryOnPage(container)).toEqual(['Vraag aan']));
  });

  it('has function, fte and period under Gegevens, until the approval', async () => {
    const { container, unmount } = renderVacancy(DRAFT, 'gegevens');
    await waitFor(() => expect(editOn(container)).not.toBeNull());
    expect(editOn(container)).toHaveAttribute('appearance', 'secondary');
    unmount();
    const approved = renderVacancy({ ...REQUESTED, status: 'approved' }, 'gegevens');
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Gegevens'),
    );
    expect(editOn(approved.container)).toBeNull();
  });

  it('says that a reader who cannot change the vacancy may only look, and who can', async () => {
    const reader = renderVacancy({ ...REQUESTED, permissions: { ...NO_PERMISSIONS } }, 'gegevens');
    await waitFor(() =>
      expect(reader.container.textContent).toContain(
        'Je kunt deze vacature bekijken. Wijzigen kan de aanvrager of wie de opdracht beheert.',
      ),
    );
    reader.unmount();
    const editor = renderVacancy(DRAFT, 'gegevens');
    await waitFor(() => expect(editOn(editor.container)).not.toBeNull());
    expect(editor.container.textContent).not.toContain('Je kunt deze vacature bekijken');
  });

  it('links the assignment from Gegevens to the assignment itself', async () => {
    const { container } = renderVacancy(REQUESTED, 'gegevens');
    await waitFor(() =>
      expect(container.querySelector('nldd-link[text="Opdracht Alfa"]')).toHaveAttribute(
        'href',
        '/opdrachten/a-1',
      ),
    );
  });
});

describe('Gegevens of a vacancy whose assignment the reader may not open', () => {
  it('names the assignment as text when the server gives no id', async () => {
    const { container } = renderVacancy({ ...REQUESTED, assignment_id: null }, 'gegevens');
    await waitFor(() => expect(container.querySelector('[text="Opdracht Alfa"]')).not.toBeNull());
    expect(container.querySelector('nldd-link[text="Opdracht Alfa"]')).toBeNull();
  });
});

describe('the part Aanvraag', () => {
  it('lists what the form asks for, filled or visibly not, each the way to fill it', async () => {
    const draft: Vacancy = {
      ...REQUESTED,
      status: 'draft',
      contract_type: null,
      scale_fits_budget_line: false,
      budget_line_scales: [12, 13],
    };
    const { container } = renderVacancy(
      draft,
      'aanvraag',
      courseAt(1, {
        mine: true,
        headline: 'Vraag de vacature aan',
        sentence: 'De aanvraag mist nog gegevens. Vul ze in; daarna vraag je de vacature aan.',
        action_text: 'Bereid aanvraag voor',
        action_href: '/vacatures/v-1/aanvraag',
        missing: ['Functienaam uit het functiegebouw', 'Soort contract'],
        task_key: 'werving.aanvraag_voorbereiden',
      }),
    );
    await waitFor(() =>
      expect(
        container.querySelector(
          'nldd-list[accessible-label="Gegevens voor het aanvraagformulier"]',
        ),
      ).not.toBeNull(),
    );
    const rows = [
      ...container.querySelectorAll(
        'nldd-list[accessible-label="Gegevens voor het aanvraagformulier"] nldd-list-item',
      ),
    ].map((row) => {
      const cells = [...row.querySelectorAll('nldd-text-cell')];
      return [
        cells[0]!.getAttribute('text'),
        cells[1]!.getAttribute('text'),
        row.querySelector('nldd-icon-cell')!.getAttribute('icon'),
        row.hasAttribute('button') || row.hasAttribute('href'),
      ];
    });
    expect(rows).toEqual([
      ['FGR-functienaam', 'Nog niet ingevuld', 'circle', true],
      ['Schaal', '11', 'check-circle-filled', true],
      ['Type contract', 'Nog niet ingevuld', 'circle', true],
      ['Aan', 'Fictief Directielid', 'check-circle-filled', true],
      ['Aanleiding en motivatie', 'Nog niet ingevuld', 'circle', true],
    ]);
    expect(
      container.querySelector('nldd-banner[variant="warning"]')?.getAttribute('text'),
    ).toContain('Schaal 11 valt buiten de tariefcategorie van de begrotingsregel');
    // The form itself is made and kept from here.
    await waitFor(() =>
      expect(container.querySelector('nldd-button[text="Maak aanvraagformulier"]')).not.toBeNull(),
    );
  });

  it('has no row for the addressee and nothing to edit for a reader without names', async () => {
    const reader: Vacancy = { ...REQUESTED, permissions: NO_PERMISSIONS };
    delete reader.addressee_name;
    delete reader.addressee_has_account;
    const { container } = renderVacancy(
      reader,
      'aanvraag',
      partsAre([REQUEST, DECISIONS, TEXT, HISTORY]),
    );
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    const labels = [...container.querySelectorAll('nldd-list nldd-list-item')].map((row) =>
      row.querySelector('nldd-text-cell')!.getAttribute('text'),
    );
    expect(labels).not.toContain('Aan');
    expect(container.querySelector('nldd-list-item[button]')).toBeNull();
    expect(tabsOf(container).map(([text]) => text)).not.toContain('Vervullen');
  });
});

describe('the motivation on Aanvraag', () => {
  const motivationRow = (container: HTMLElement) =>
    [...container.querySelectorAll('nldd-list-item')].find(
      (row) =>
        row.querySelector('nldd-text-cell')?.getAttribute('text') === 'Aanleiding en motivatie',
    );

  it('links to the text only when the server gives the row Tekst', async () => {
    const withRow = renderVacancy(REQUESTED, 'aanvraag');
    await waitFor(() => expect(motivationRow(withRow.container)).toBeDefined());
    expect(motivationRow(withRow.container)).toHaveAttribute('href', '/vacatures/v-1/tekst');
    withRow.unmount();
    const without = renderVacancy(
      REQUESTED,
      'aanvraag',
      partsAre([REQUEST, DECISIONS, DETAILS, HISTORY]),
    );
    await waitFor(() => expect(motivationRow(without.container)).toBeDefined());
    expect(motivationRow(without.container)).not.toHaveAttribute('href');
    expect(motivationRow(without.container)).not.toHaveAttribute('button');
  });
});

describe('a task at the request form', () => {
  const FORMS = '/api/vacancies/v-1/request-forms';
  const forms = (current: unknown) => ({
    available: true,
    may_make: true,
    missing: [],
    current,
    earlier: [],
    changed: [],
    signed: [],
  });
  const next = (task: string, text: string) =>
    courseAt(2, {
      mine: true,
      headline: text,
      sentence: `${text}.`,
      action_text: text,
      action_href: '/vacatures/v-1/aanvraag',
      task_key: task,
    });
  const MADE = { id: 'f-1', made_at: '2026-11-01T09:00:00Z' };

  it.each([
    ['werving.formulier_maken', 'Maak aanvraagformulier', null, 'Maak aanvraagformulier'],
    [
      'werving.getekend_formulier_vastleggen',
      'Leg getekend formulier vast',
      MADE,
      'Leg het getekende formulier vast',
    ],
  ])(
    '%s opens the request itself, with the step as its button',
    async (task, text, made, there) => {
      const { container } = renderVacancy(REQUESTED, '', {
        ...next(task, text),
        [FORMS]: forms(made),
      });
      await waitFor(() => expect(primaryOnPage(container)).toEqual([text]));
      fireEvent.click(container.querySelector(`nldd-button[text="${text}"]`)!);
      await waitFor(() =>
        expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Aanvraag'),
      );
      await waitFor(() => expect(primaryOnPage(container)).toEqual([there]));
    },
  );
});

describe('the part Advies en akkoord', () => {
  it('shows the three decisions in columns and makes the next one to record primary', async () => {
    const adviser: Vacancy = {
      ...REQUESTED,
      permissions: { ...NO_PERMISSIONS, can_record_hr_advice: true },
    };
    const { container } = renderVacancy(adviser, 'advies');
    await waitFor(() =>
      expect(
        container.querySelector('nldd-table[accessible-label="Advies en akkoord"]'),
      ).not.toBeNull(),
    );
    const rows = [...container.querySelectorAll('nldd-table-row:not([slot])')].map((row) =>
      [...row.querySelectorAll('nldd-text-cell')].map((cell) => cell.getAttribute('text')),
    );
    expect(rows).toEqual([
      ['Nog geen besluit', 'Fictieve Adviseur'],
      ['Nog niemand genoemd', ''],
      ['Nog niemand genoemd', ''],
    ]);
    // The row is the way in: the one the reader may record opens on its name,
    // and no row holds a text button.
    expect(
      [...container.querySelectorAll('nldd-table nldd-link')].map((link) =>
        link.getAttribute('text'),
      ),
    ).toEqual(['Advies HR']);
    expect(container.querySelectorAll('nldd-table nldd-button')).toHaveLength(0);
    // On the part of the current step the head has no button; the part has the one.
    expect(primaryOnPage(container)).toEqual(['Leg advies HR vast']);
    expect(tabsOf(container).find(([, current]) => current)?.[0]).toBe('Advies en akkoord');
  });
});

const TEXT_WORK = {
  vacancy_id: 'v-1',
  publications: [],
  may_record_publication: false,
  publication_missing: false,
  drafting_available: false,
  reviewer_options: [{ id: 'p-2', name: 'Fictieve Adviseur' }],
  texts: [
    {
      kind: 'motivation',
      needed: true,
      state: 'in_review',
      state_text: 'Ter beoordeling',
      with_whom: 'Wacht op het oordeel van Fictieve Adviseur',
      revising: false,
      open_passages: [],
      action: { key: 'withdraw', text: 'Neem terug om verder te schrijven' },
      may_write: false,
      may_remark: true,
      may_settle: false,
      versions: [
        {
          id: 't-1',
          number: 1,
          body: 'De rol is nodig voor de opdracht.',
          source: 'human',
          created_at: '2026-10-01T09:00:00Z',
          created_by_name: 'Fictieve Eigenaar',
          by_viewer: true,
        },
      ],
      rounds: [
        {
          id: 'r-1',
          round: 1,
          version_number: 1,
          offered_at: '2026-10-02T09:00:00Z',
          withdrawn: false,
          outcome: 'open',
          verdicts: [{ reviewer_name: 'Fictieve Adviseur', is_viewer: false }],
        },
      ],
      remarks: [],
      latest_changes: [],
    },
    {
      kind: 'vacancy_text',
      needed: true,
      state: 'returned',
      state_text: 'Terug met opmerkingen',
      with_whom: 'Terug bij Fictieve Eigenaar',
      revising: false,
      open_passages: ['[vul aan: de datum tot wanneer reageren kan]'],
      action: { key: 'process', text: 'Verwerk de opmerkingen' },
      may_write: true,
      may_remark: true,
      may_settle: false,
      standard_text: { role: 'Software engineer', match: 'role', unread: false, missing: [] },
      versions: [
        {
          id: 't-2',
          number: 1,
          body: 'Eerste opzet.',
          source: 'template',
          origin: 'Uit de standaardtekst Software engineer, versie 2026-10-08',
          created_at: '2026-10-01T09:00:00Z',
          by_viewer: true,
        },
        {
          id: 't-3',
          number: 2,
          body: 'Bouw mee.\n\n## Dit ga je doen\n\nJe bouwt.\n\n- ontwerpen\n- testen',
          source: 'human',
          created_at: '2026-10-03T09:00:00Z',
          created_by_name: 'Fictieve Eigenaar',
          by_viewer: true,
        },
      ],
      rounds: [
        {
          id: 'r-2',
          round: 1,
          version_number: 2,
          offered_at: '2026-10-04T09:00:00Z',
          withdrawn: false,
          outcome: 'returned',
          verdicts: [
            {
              reviewer_name: 'Fictieve Adviseur',
              is_viewer: false,
              verdict: 'remarks',
              note: 'Maak de eisen concreter.',
            },
          ],
        },
      ],
      remarks: [
        {
          id: 'm-1',
          section: 'Dit ga je doen',
          body: 'Te algemeen.',
          version_number: 2,
          created_at: '2026-10-04T10:00:00Z',
          author_name: 'Fictieve Adviseur',
          by_viewer: false,
          answers: [],
        },
      ],
      latest_changes: [
        { heading: 'Dit ga je doen', change: 'added', summary: 'Dit ga je doen: toegevoegd.' },
      ],
    },
  ],
};

describe('the part Tekst en openstellen', () => {
  const WORK_PATH = '/api/vacancies/v-1/text-work';

  it('shows where each text stands, who has it and one next step', async () => {
    const { container } = renderVacancy(REQUESTED, 'tekst', { [WORK_PATH]: TEXT_WORK });
    await waitFor(() => expect(container.textContent).toContain('Je bouwt.'));
    expect(
      [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
        el.getAttribute('text'),
      ),
    ).toEqual(['Aanleiding en motivatie', 'Vacaturetekst', 'Procedure']);
    expect(
      [...container.querySelectorAll('nldd-tag')].map((el) => el.getAttribute('text')),
    ).toEqual(expect.arrayContaining(['Ter beoordeling', 'Terug met opmerkingen']));
    expect(container.textContent).toContain('Wacht op het oordeel van Fictieve Adviseur');
    // The text reads as sections: a heading and a list, not raw marks.
    expect(
      container.querySelector('nldd-title[text="Dit ga je doen"]')?.getAttribute('heading-level'),
    ).toBe('3');
    expect(
      [...container.querySelectorAll('nldd-rich-text li')].map((el) => el.textContent),
    ).toEqual(['ontwerpen', 'testen']);
    expect(container.textContent).not.toContain('## ');
    // The head has no step here, so the accent is on this part: the next step
    // of the text that leads. Everything else is a plain
    // button, never bare text.
    const within = (text: string) =>
      container.querySelector(`nldd-button[text="${text}"]`)?.getAttribute('appearance');
    expect(within('Verwerk de opmerkingen')).toBe('primary');
    expect(within('Neem terug om verder te schrijven')).toBe('secondary');
    expect(container.querySelectorAll('nldd-button[appearance="primary"]')).toHaveLength(1);
    expect(
      container.querySelectorAll('nldd-button[appearance="neutral-transparent"]'),
    ).toHaveLength(
      [...container.querySelectorAll('nldd-button')].filter((el) =>
        ['Antwoord', 'Markeer als afgehandeld', 'Zet weer open'].includes(
          el.getAttribute('text') ?? '',
        ),
      ).length,
    );
    // The round, the remark and what still has to be filled in.
    expect(container.textContent).toContain('terug met opmerkingen (Fictieve Adviseur)');
    expect(container.textContent).toContain('Dit ga je doen: Te algemeen.');
    expect(container.textContent).toContain('Fictieve Adviseur: Maak de eisen concreter.');
    // What is still open is a count; the passages themselves are in the editor.
    expect(container.textContent).toContain('Nog 1 plek in te vullen');
    expect(container.textContent).not.toContain('[vul aan:');
    expect(container.querySelector('nldd-button[text="Toon eerdere versies (1)"]')).not.toBeNull();
    expect(container.textContent).not.toContain('Eerste opzet.');
    // No model is set up: a tailored draft is not offered, and nothing says so.
    expect(container.querySelector('nldd-button[text="Stel een tekst op maat op"]')).toBeNull();
    expect(container.textContent).not.toContain('taalmodel');
    expect(container.querySelector('nldd-button[text="Schrijf zelf"]')).toBeNull();
  });

  it('says so when a tailored draft was written without the context from the corpus, and only then', async () => {
    const LINE = 'Opgesteld zonder de context uit het corpus: dat was niet bereikbaar.';
    for (const [context, shown] of [
      ['unreachable', true],
      ['used', false],
      [undefined, false],
    ] as const) {
      const { container, unmount } = renderVacancy(REQUESTED, 'tekst', {
        [WORK_PATH]: { ...TEXT_WORK, ...(context ? { context } : {}) },
      });
      await waitFor(() => expect(container.textContent).toContain('Je bouwt.'));
      expect(container.textContent?.includes(LINE)).toBe(shown);
      unmount();
    }
  });

  it('starts an empty vacancy text from the standard text, with a tailored draft next to it', async () => {
    const empty = {
      ...TEXT_WORK,
      drafting_available: true,
      texts: [
        {
          ...TEXT_WORK.texts[1],
          state: 'none',
          state_text: 'Nog niet begonnen',
          with_whom: null,
          open_passages: [],
          action: { key: 'start', text: 'Begin met de standaardtekst' },
          versions: [],
          rounds: [],
          remarks: [],
          latest_changes: [],
        },
      ],
    };
    const { container } = renderVacancy(REQUESTED, 'tekst', { [WORK_PATH]: empty });
    await waitFor(() =>
      expect(
        container.querySelector('nldd-button[text="Begin met de standaardtekst"]'),
      ).not.toBeNull(),
    );
    expect(
      container
        .querySelector('nldd-button[text="Begin met de standaardtekst"]')
        ?.getAttribute('appearance'),
      // The head has no step here, so this next step is the accent.
    ).toBe('primary');
    expect(
      container
        .querySelector('nldd-button[text="Stel een tekst op maat op"]')
        ?.getAttribute('appearance'),
    ).toBe('secondary');
    expect(container.querySelector('nldd-button[text="Schrijf zelf"]')).not.toBeNull();
    expect(container.textContent).toContain('Er is een standaardtekst voor Software engineer.');
  });

  it('puts a link still to record above the texts, as the step of the page', async () => {
    const settled = {
      ...TEXT_WORK.texts[1],
      state: 'settled',
      action: { key: 'revise', text: 'Pas de vastgestelde tekst aan' },
    };
    const { container } = renderVacancy(REQUESTED, 'tekst', {
      [WORK_PATH]: {
        ...TEXT_WORK,
        texts: [settled],
        may_record_publication: true,
        publication_missing: true,
      },
    });
    const step = () =>
      container.querySelector('nldd-button[text="Leg de link naar de vacature vast"]');
    await waitFor(() => expect(step()).not.toBeNull());
    expect(step()).toHaveAttribute('appearance', 'primary');
    const titles = [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
      el.getAttribute('text'),
    );
    expect(titles).toEqual(['Gepubliceerd', 'Vacaturetekst', 'Procedure']);
  });

  it('shows where the vacancy is published as the closing fact', async () => {
    const published = {
      ...TEXT_WORK,
      texts: [],
      may_record_publication: true,
      publications: [
        {
          id: 'pub-1',
          place: 'government_wide',
          place_text: 'Werken voor Nederland',
          url: 'https://vacatures.example/v/1',
          published_on: '2026-10-08',
        },
      ],
    };
    const { container } = renderVacancy(REQUESTED, 'tekst', { [WORK_PATH]: published });
    await waitFor(() =>
      expect(container.textContent).toContain(
        'Gepubliceerd op Werken voor Nederland op 8 okt 2026',
      ),
    );
    expect(
      container.querySelector(
        'nldd-button[text="Bekijk de vacature"], nldd-link[text="Bekijk de vacature"]',
      ),
    ).not.toBeNull();
  });
});

describe('the procedure under Tekst en openstellen', () => {
  it('shows the steps with their dates and the minimum before it starts', async () => {
    const { container } = renderVacancy(REQUESTED, 'tekst');
    await waitFor(() =>
      expect(
        container.querySelector('nldd-text-cell[text="5. Interne openstelling"]'),
      ).not.toBeNull(),
    );
    expect(
      container
        .querySelector('nldd-text-cell[text="5. Interne openstelling"]')
        ?.getAttribute('supporting-text'),
    ).toBe('Duurt minimaal 5 werkdagen');
    expect(container.querySelector('nldd-text-cell[text="Nog niet gestart"]')).not.toBeNull();
  });
});

describe('the part Vervullen', () => {
  it('shows the reference in the recruitment system and who was hired, with links', async () => {
    const filled: Vacancy = { ...REQUESTED, status: 'filled' };
    const { container } = renderVacancy(filled, 'vervulling', {
      '/api/vacancies/v-1/hire': HIRE,
    });
    await waitFor(() =>
      expect(container.querySelector('nldd-link[text="Fictieve Collega"]')).not.toBeNull(),
    );
    expect(
      container.querySelector('nldd-link[text="Fictieve Collega"]')?.getAttribute('href'),
    ).toBe('/mensen/p-7');
    expect(container.querySelector('nldd-link[text="V-2026-014"]')?.getAttribute('href')).toBe(
      'https://werving.example/v/14',
    );
    expect(container.querySelector('nldd-text-cell[text="Emply"]')).not.toBeNull();
    expect(container.querySelector('nldd-text-cell[text="4 jan 2027"]')).not.toBeNull();
    expect(
      container.querySelector('nldd-link[text="Team van Opdracht Alfa"]')?.getAttribute('href'),
    ).toBe('/opdrachten/a-1/team');
    expect(container.querySelector('nldd-button[text="Aanname gaat niet door"]')).not.toBeNull();
    // Filled: no primary action left.
    expect(primaryOnPage(container)).toEqual([]);
  });

  it('offers to fill here when the next step of the reader is another one', async () => {
    const open: Vacancy = {
      ...REQUESTED,
      status: 'open',
      permissions: { ...REQUESTED.permissions, can_fill: true },
    };
    const { container } = renderVacancy(open, 'vervulling', {
      ...partsAre([
        REQUEST,
        DECISIONS,
        part('text', 'Tekst en openstellen', 'current', 'Leg de link vast'),
        part('fulfilment', 'Vervullen', 'current', 'Leg vast wie is aangenomen'),
        DETAILS,
        HISTORY,
      ]),
      '/api/vacancies/v-1/hire': { vacancy_id: 'v-1', recruitment_ref: null, hire: null },
      ...courseAt(4, {
        mine: true,
        headline: 'Leg de link vast',
        sentence: 'Leg de link vast.',
        action_text: 'Leg de link vast',
        action_href: '/vacatures/v-1/tekst',
        task_key: 'werving.link_vastleggen',
      }),
    });
    await waitFor(() =>
      expect(container.querySelector('nldd-button[text="Vervul"]')).toHaveAttribute(
        'appearance',
        'primary',
      ),
    );
    expect(primaryOnPage(container)).toEqual(['Vervul']);
  });

  it('offers to fill an open vacancy from the head, once', async () => {
    const open: Vacancy = {
      ...REQUESTED,
      status: 'open',
      permissions: {
        ...REQUESTED.permissions,
        can_fill: true,
        can_withdraw: true,
      },
    };
    const { container } = renderVacancy(open, 'vervulling', {
      '/api/vacancies/v-1/hire': {
        vacancy_id: 'v-1',
        recruitment_ref: null,
        hire: null,
      },
      ...courseAt(4, {
        mine: true,
        headline: 'Leg vast wie is aangenomen',
        sentence: 'De vacature kan worden vervuld. Leg vast wie is aangenomen.',
        action_text: 'Vervul',
        action_href: '/vacatures/v-1/vervulling',
        task_key: 'werving.vervullen',
      }),
    });
    await waitFor(() =>
      expect(container.querySelector('nldd-button[text="Leg verwijzing vast"]')).not.toBeNull(),
    );
    await waitFor(() => expect(primaryOnPage(container)).toEqual(['Vervul']));
    expect(container.querySelectorAll('nldd-button[text="Vervul"]')).toHaveLength(1);
    expect(container.textContent).toContain('Nog niemand aangenomen voor 0,8 fte');
    expect(container.querySelector('nldd-button[text="Trek vacature in"]')).not.toBeNull();
    // The hire sheet asks who and from when; it is in the document, closed.
    const hire = [...document.body.querySelectorAll('nldd-sheet')].find((sheet) =>
      sheet.querySelector('nldd-top-title-bar')?.getAttribute('text')?.includes('vervullen'),
    )!;
    expect(hire.hasAttribute('open')).toBe(false);
    expect(
      [...hire.querySelectorAll('nldd-form-field')].map((field) => field.getAttribute('label')),
    ).toEqual(['Naam van de nieuwe collega', 'Start op']);
    expect(hire.querySelector('nldd-checkbox-field')?.getAttribute('label')).toBe(
      'Plan de inzet meteen op de begrotingsregel',
    );
  });
});
