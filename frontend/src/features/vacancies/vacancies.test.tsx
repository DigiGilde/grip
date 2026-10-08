import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { renderApp } from '@/test/utils';
import type { TextVersion, Vacancy, VacancyOptions, VacancySummary } from './api';
import { parseFte, parseScale } from './hooks';
import { originOf, publishedOrigin, scaleAndFte } from './labels';
import { OpenRolesPage } from './OpenRolesPage';
import { VacanciesPage } from './VacanciesPage';
import { VacancyDetailPage } from './VacancyDetailPage';

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
  id: 't-1',
  kind: 'vacancy_text',
  body: 'Concept van het model.',
  source: 'model',
  model_id: 'testmodel-1',
  prompt_version: 'v1',
  created_at: '2026-10-01T09:00:00Z',
  model_assisted: true,
  origin_model_id: 'testmodel-1',
  origin_drafted_at: '2026-10-01T09:00:00Z',
  is_current: false,
};

const FULL: Vacancy = {
  id: 'v-1',
  function_title: 'Backend-ontwikkelaar',
  scale: 11,
  fte: '0.80',
  status: 'requested',
  declarable: true,
  vacancy_type: 'regulier',
  contract_type: 'temporary_project',
  channels: [],
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
    { kind: 'hr_advice', label: 'Advies HR', person_name: 'Fictieve Adviseur', has_account: true },
  ],
  texts: [MODEL_DRAFT],
  requester_name: 'Fictieve Eigenaar',
  addressee_name: 'Fictief Directielid',
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

/** Answers GET requests from a table of path to body; anything else is a 404. */
function stubApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).split('?')[0] ?? '';
    if (path in routes) {
      return new Response(JSON.stringify(routes[path]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response(
      JSON.stringify({ type: 'about:blank', title: 'Niet gevonden', status: 404 }),
      { status: 404, headers: { 'Content-Type': 'application/problem+json' } },
    );
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function renderDetail(id: string) {
  return renderApp(
    <Routes>
      <Route path={PATHS.vacancyDetail} element={<VacancyDetailPage />} />
    </Routes>,
    { path: `/vacatures/${id}` },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('helpers', () => {
  it('reads fte with a comma or a point', () => {
    expect(parseFte('0,8')).toBe('0.8');
    expect(parseFte('1')).toBe('1');
    expect(parseFte('0')).toBeNull();
    expect(parseFte('veel')).toBeNull();
  });

  it('reads a scale, empty or not', () => {
    expect(parseScale('')).toBeNull();
    expect(parseScale('11')).toBe(11);
    expect(parseScale('25')).toBeUndefined();
    expect(parseScale('elf')).toBeUndefined();
  });

  it('describes scale and fte', () => {
    expect(scaleAndFte(11, '0.80')).toBe('Schaal 11, 0,8 fte');
    expect(scaleAndFte(null, '1.00')).toBe('1 fte');
  });

  it('says where a version came from', () => {
    expect(originOf(MODEL_DRAFT)).toContain('Opgesteld door een taalmodel (testmodel-1)');
    const rewritten: TextVersion = { ...MODEL_DRAFT, id: 't-2', source: 'human', model_id: null };
    expect(originOf(rewritten)).toContain('op basis van een concept van een taalmodel');
    const human: TextVersion = { ...rewritten, model_assisted: false };
    expect(originOf(human)).not.toContain('taalmodel');
    expect(publishedOrigin(PUBLIC.published_text!)).toContain('Een taalmodel (testmodel-1)');
  });
});

describe('VacanciesPage', () => {
  const SUMMARY: VacancySummary = {
    id: 'v-1',
    function_title: 'Backend-ontwikkelaar',
    scale: 11,
    fte: '0.80',
    status: 'requested',
    assignment_name: 'Opdracht Alfa',
    next_step: 'Advies HR',
  };

  it('lists vacancies as links, with status and next step', async () => {
    stubApi({
      '/api/vacancies': [SUMMARY],
      '/api/vacancies/unfilled-roles': [],
      '/api/vacancies/options': OPTIONS,
    });
    const { container } = renderApp(<VacanciesPage />);
    await waitFor(() => expect(container.querySelector('nldd-list-item')).not.toBeNull());
    const row = container.querySelector('nldd-list-item')!;
    expect(row.getAttribute('href')).toBe('/vacatures/v-1');
    const cells = [...row.querySelectorAll('nldd-text-cell')];
    expect(cells[0]!.getAttribute('text')).toBe('Backend-ontwikkelaar');
    expect(cells[0]!.getAttribute('supporting-text')).toBe('Opdracht Alfa · Schaal 11, 0,8 fte');
    expect(cells[1]!.getAttribute('text')).toBe('Aangevraagd');
    expect(cells[1]!.getAttribute('supporting-text')).toBe('Volgende stap: Advies HR');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Vacatures');
  });

  it('offers a new vacancy only to who may create one', async () => {
    stubApi({
      '/api/vacancies': [],
      '/api/vacancies/unfilled-roles': [],
      '/api/vacancies/options': OPTIONS,
    });
    const { container, unmount } = renderApp(<VacanciesPage />);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(container.querySelector('nldd-button[text="Nieuwe vacature"]')).toBeNull();
    expect(container.querySelector('nldd-button[text="Formulier en taalmodel"]')).toBeNull();
    expect(container.querySelector('nldd-button[text="Open rollen"]')).not.toBeNull();
    expect(container.querySelector('nldd-inline-dialog[slot="empty"]')).not.toBeNull();
    unmount();

    stubApi({
      '/api/vacancies': [],
      '/api/vacancies/unfilled-roles': [],
      '/api/vacancies/options': {
        ...OPTIONS,
        can_create_without_budget_line: true,
        can_manage_setup: true,
      },
    });
    const second = renderApp(<VacanciesPage />);
    await waitFor(() =>
      expect(second.container.querySelector('nldd-button[text="Nieuwe vacature"]')).not.toBeNull(),
    );
    expect(
      second.container.querySelector('nldd-button[text="Formulier en taalmodel"]'),
    ).not.toBeNull();
  });

  it('shows an error when the list cannot be loaded', async () => {
    stubApi({ '/api/vacancies/options': OPTIONS, '/api/vacancies/unfilled-roles': [] });
    const { container } = renderApp(<VacanciesPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-banner[variant="critical"]')).not.toBeNull(),
    );
  });
});

describe('VacancyDetailPage', () => {
  it('shows the full vacancy with its sections to who may edit', async () => {
    stubApi({
      '/api/vacancies/v-1': FULL,
      '/api/vacancies/options': OPTIONS,
      '/api/vacancies/v-1/request-form/status': {
        available: false,
        open_fields: [],
        motivation_established: false,
      },
    });
    const { container } = renderDetail('v-1');
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Backend-ontwikkelaar'),
    );
    const headings = [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
      el.getAttribute('text'),
    );
    expect(headings).toEqual([
      'Gegevens',
      'Advies en akkoord',
      'Procedure',
      'Teksten',
      'Aanvraagformulier',
    ]);
    expect(container.querySelector('nldd-text-cell[overline="Aan"]')?.getAttribute('text')).toBe(
      'Fictief Directielid',
    );
    // The minimum of the internal opening is visible before it starts.
    expect(
      container
        .querySelector('nldd-text-cell[text="5. Interne openstelling"]')
        ?.getAttribute('supporting-text'),
    ).toBe('Duurt minimaal 5 werkdagen');
    // A model draft says so, and can be established by a person.
    expect(container.textContent).toContain('Opgesteld door een taalmodel (testmodel-1)');
    expect(container.querySelector('nldd-button[text="Stel vast"]')).not.toBeNull();
    // Drafting is offered but switched off while no model is set up.
    const draftButtons = container.querySelectorAll(
      'nldd-button[text="Laat een concept opstellen"]',
    );
    expect(draftButtons).toHaveLength(2);
    draftButtons.forEach((button) => expect(button.hasAttribute('disabled')).toBe(true));
    expect(container.textContent).toContain('Het taalmodel is in deze instantie niet ingesteld');
    // Requested, so no request button any more; details still editable.
    expect(container.querySelector('nldd-button[text="Vraag aan"]')).toBeNull();
    expect(container.querySelector('nldd-button[text="Bewerk gegevens"]')).not.toBeNull();
    // The adviser is named but has not decided; this viewer may only rename.
    expect(container.querySelector('nldd-button[text="Wijzig hr-adviseur"]')).not.toBeNull();
    expect(container.querySelector('nldd-button[text="Leg advies hr vast"]')).toBeNull();
  });

  it('enables drafting when the model is set up', async () => {
    stubApi({
      '/api/vacancies/v-1': FULL,
      '/api/vacancies/options': { ...OPTIONS, drafting_available: true },
      '/api/vacancies/v-1/request-form/status': {
        available: true,
        file_name: 'formulier.pdf',
        open_fields: [{ source: 'motivation', label: 'Aanleiding en motivatie (vastgesteld)' }],
        motivation_established: false,
      },
    });
    const { container } = renderDetail('v-1');
    await waitFor(() =>
      expect(
        container.querySelector('nldd-button[text="Download ingevuld formulier (pdf)"]'),
      ).not.toBeNull(),
    );
    const draft = container.querySelector('nldd-button[text="Laat een concept opstellen"]')!;
    expect(draft.hasAttribute('disabled')).toBe(false);
    const download = container.querySelector(
      'nldd-button[text="Download ingevuld formulier (pdf)"]',
    )!;
    expect(download.getAttribute('href')).toBe('/api/vacancies/v-1/request-form');
    expect(
      container.querySelector('nldd-text-cell[text="Aanleiding en motivatie (vastgesteld)"]'),
    ).not.toBeNull();
  });

  it('shows only the public view to someone without a role', async () => {
    stubApi({ '/api/vacancies/v-2': PUBLIC, '/api/vacancies/options': OPTIONS });
    const { container } = renderDetail('v-2');
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Productmanager'),
    );
    expect(container.textContent).toContain('Wij zoeken een productmanager.');
    expect(container.textContent).toContain('Een taalmodel (testmodel-1)');
    const headings = [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
      el.getAttribute('text'),
    );
    expect(headings).toEqual(['Vacaturetekst']);
    expect(container.querySelector('nldd-button[text="Bewerk gegevens"]')).toBeNull();
    // No sheet at all: nothing to edit in the public view.
    expect(document.body.querySelector('nldd-sheet')).toBeNull();
  });

  it('says so when the vacancy is not there or not visible', async () => {
    stubApi({ '/api/vacancies/options': OPTIONS });
    const { container } = renderDetail('v-9');
    await waitFor(() =>
      expect(
        container.querySelector('nldd-inline-dialog[text="Deze vacature is niet gevonden"]'),
      ).not.toBeNull(),
    );
  });
});

describe('OpenRolesPage', () => {
  it('shows every open role with its text and origin', async () => {
    stubApi({
      '/api/vacancies/open-roles': [
        {
          id: 'v-2',
          function_title: 'Productmanager',
          scale: 13,
          fte: '1.00',
          text: PUBLIC.published_text,
        },
      ],
    });
    const { container } = renderApp(<OpenRolesPage />);
    await waitFor(() => expect(container.textContent).toContain('Wij zoeken een productmanager.'));
    expect(container.querySelector('nldd-title[text="Productmanager"]')).not.toBeNull();
    expect(container.textContent).toContain('Schaal 13, 1 fte');
    expect(container.textContent).toContain('Vastgesteld door een mens');
  });

  it('has an empty state', async () => {
    stubApi({ '/api/vacancies/open-roles': [] });
    const { container } = renderApp(<OpenRolesPage />);
    await waitFor(() =>
      expect(
        container.querySelector('nldd-inline-dialog[text="Er staan nu geen rollen open"]'),
      ).not.toBeNull(),
    );
  });
});
