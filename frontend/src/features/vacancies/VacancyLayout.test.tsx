import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { renderApp } from '@/test/utils';
import type { TextVersion, Vacancy, VacancyHire, VacancyOptions } from './api';
import { VACANCY_TAB_SEGMENTS } from './paths';
import { visibleTabs } from './shell';
import { DecisionsTab, FulfilmentTab, ProcedureTab, RequestTab, TextTab } from './tabs/VacancyTabs';
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

function renderVacancy(vacancy: Vacancy, tab = '', extra: Record<string, unknown> = {}) {
  stubApi({
    [`/api/vacancies/${vacancy.id}`]: vacancy,
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
        <Route index element={<RequestTab />} />
        <Route path={VACANCY_TAB_SEGMENTS.decisions} element={<DecisionsTab />} />
        <Route path={VACANCY_TAB_SEGMENTS.text} element={<TextTab />} />
        <Route path={VACANCY_TAB_SEGMENTS.procedure} element={<ProcedureTab />} />
        <Route path={VACANCY_TAB_SEGMENTS.fulfilment} element={<FulfilmentTab />} />
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

/** Position (from 1) of the step the bar marks as current. */
function currentStep(container: HTMLElement): number {
  const items = [...container.querySelectorAll('nldd-step-bar-item')];
  return items.findIndex((item) => item.getAttribute('status') === 'current') + 1;
}

describe('the header of a vacancy', () => {
  it('says what it is, where it belongs and where it stands, with one primary action', async () => {
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
    await waitFor(() => expect(currentStep(container)).toBe(2));
    // The course says where it stands, so no tag repeats it; the sentence
    // says whose move it is.
    expect(container.querySelector('nldd-badge[text="Aangevraagd"]')).toBeNull();
    expect(container.textContent).toContain('Je wacht op het advies van HR.');
    // The assignment links to its Bemensing tab.
    expect(container.querySelector('nldd-link[text="Opdracht Alfa"]')?.getAttribute('href')).toBe(
      '/opdrachten/a-1/bemensing',
    );
    expect(container.textContent).toContain('Regulier · Schaal 11, 0,8 fte');
    expect(tabsOf(container)).toEqual([
      ['Aanvraag', true],
      ['Taken', false],
      ['Advies en akkoord', false],
      ['Tekst', false],
      ['Procedure', false],
      ['Vervulling', false],
      ['Geschiedenis', false],
    ]);
    // Someone else has the move: nothing on the page takes the accent.
    expect(primaryOnPage(container)).toEqual([]);
    expect(container.querySelectorAll('h1')).toHaveLength(1);
  });

  it('leaves out the tab a reader has nothing on', () => {
    expect(visibleTabs(REQUESTED)).toContain('fulfilment');
    const reader = { ...REQUESTED, permissions: NO_PERMISSIONS };
    expect(visibleTabs(reader)).toEqual([
      'request',
      'tasks',
      'decisions',
      'text',
      'procedure',
      'history',
    ]);
    expect(visibleTabs(PUBLIC)).toEqual([]);
  });

  it('shows the published text and nothing to do to someone without a role', async () => {
    const { container } = renderVacancy(PUBLIC);
    await waitFor(() => expect(container.textContent).toContain('Wij zoeken een productmanager.'));
    expect(container.textContent).toContain('Een taalmodel (testmodel-1)');
    expect(container.querySelector('nldd-menu-bar')).toBeNull();
    expect(container.querySelector('nldd-step-bar')).toBeNull();
    expect(container.querySelector('nldd-button')).toBeNull();
    expect(document.body.querySelector('nldd-sheet')).toBeNull();
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

  it('carries the one primary action when the vacancy is approved', async () => {
    const approved: Vacancy = { ...REQUESTED, status: 'approved' };
    const { container } = renderVacancy(
      approved,
      'procedure',
      courseAt(3, {
        mine: true,
        headline: 'Stel de vacature open',
        sentence: 'Het akkoord is gegeven. Stel de vacature open.',
        action_text: 'Stel open',
        action_href: '/vacatures/v-1/procedure',
        task_key: 'werving.openstellen',
      }),
    );
    await waitFor(() =>
      expect(
        container.querySelector('nldd-table[accessible-label="Stappen van de procedure"]'),
      ).not.toBeNull(),
    );
    // "Stel open" once, in the header; the procedure tab has no primary of its own.
    await waitFor(() => expect(primaryOnPage(container)).toEqual(['Stel open']));
    expect(container.querySelectorAll('nldd-button[text="Stel open"]')).toHaveLength(1);
  });
});

describe('the Aanvraag tab', () => {
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
      '',
      courseAt(1, {
        mine: true,
        headline: 'Vraag de vacature aan',
        sentence: 'De aanvraag mist nog gegevens. Vul ze in; daarna vraag je de vacature aan.',
        action_text: 'Bereid aanvraag voor',
        action_href: '/vacatures/v-1',
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
    // A fresh vacancy: the course is at its first step, the head carries the
    // one primary action and says what still stands in its way.
    await waitFor(() => expect(currentStep(container)).toBe(1));
    expect(primaryOnPage(container)).toEqual(['Bereid aanvraag voor']);
    expect(container.textContent).toContain(
      'Ontbreekt nog: Functienaam uit het functiegebouw, Soort contract.',
    );
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
    const { container } = renderVacancy(reader);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    const labels = [...container.querySelectorAll('nldd-list nldd-list-item')].map((row) =>
      row.querySelector('nldd-text-cell')!.getAttribute('text'),
    );
    expect(labels).not.toContain('Aan');
    expect(container.querySelector('nldd-list-item[button]')).toBeNull();
    expect(
      container.querySelector('nldd-button[text="Wijzig functie, fte of periode"]'),
    ).toBeNull();
    expect(tabsOf(container).map(([text]) => text)).not.toContain('Vervulling');
  });
});

describe('the Advies en akkoord tab', () => {
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
    // On the tab of the current step the header has no button; the tab has the one.
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

describe('the Tekst tab', () => {
  const WORK_PATH = '/api/vacancies/v-1/text-work';

  it('shows where each text stands, who has it and one next step', async () => {
    const { container } = renderVacancy(REQUESTED, 'tekst', { [WORK_PATH]: TEXT_WORK });
    await waitFor(() => expect(container.textContent).toContain('Je bouwt.'));
    expect(
      [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
        el.getAttribute('text'),
      ),
    ).toEqual(['Aanleiding en motivatie', 'Vacaturetekst']);
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
    // The header only points to another tab here, so the accent is on this
    // tab: the next step of the text that leads. Everything else is a plain
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
      // The header only points to another tab, so this next step is the accent.
    ).toBe('primary');
    expect(
      container
        .querySelector('nldd-button[text="Stel een tekst op maat op"]')
        ?.getAttribute('appearance'),
    ).toBe('secondary');
    expect(container.querySelector('nldd-button[text="Schrijf zelf"]')).not.toBeNull();
    expect(container.textContent).toContain('Er is een standaardtekst voor Software engineer.');
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

describe('the Procedure tab', () => {
  it('shows the steps with their dates and the minimum before it starts', async () => {
    const { container } = renderVacancy(REQUESTED, 'procedure');
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

describe('the Vervulling tab', () => {
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
    ).toBe('/team/p-7');
    expect(container.querySelector('nldd-link[text="V-2026-014"]')?.getAttribute('href')).toBe(
      'https://werving.example/v/14',
    );
    expect(container.querySelector('nldd-text-cell[text="Emply"]')).not.toBeNull();
    expect(container.querySelector('nldd-text-cell[text="4 jan 2027"]')).not.toBeNull();
    expect(
      container
        .querySelector('nldd-link[text="Bemensing van Opdracht Alfa"]')
        ?.getAttribute('href'),
    ).toBe('/opdrachten/a-1/bemensing');
    expect(container.querySelector('nldd-button[text="Aanname gaat niet door"]')).not.toBeNull();
    // Filled: no step bar and no primary action left.
    expect(container.querySelector('nldd-step-bar')).toBeNull();
    expect(primaryOnPage(container)).toEqual([]);
  });

  it('offers to fill an open vacancy from the step bar, once', async () => {
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
