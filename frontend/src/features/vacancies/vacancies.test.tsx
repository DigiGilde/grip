import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import type { TextVersion, Vacancy, VacancyOptions, VacancySummary } from './api';
import { parseFte, parseScale } from './hooks';
import { originOf, publishedOrigin, scaleAndFte } from './labels';
import { OpenRolesPage } from './OpenRolesPage';
import { VacanciesPage } from './VacanciesPage';

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
    vacancy_type: 'regulier',
    next_step: 'Advies HR',
    step: 'decide',
    step_detail: 'Wacht op advies HR',
    step_since: '2026-01-05',
  };

  it('lists vacancies in aligned columns, with the next step and the status', async () => {
    stubApi({
      '/api/vacancies': [SUMMARY],
      '/api/vacancies/unfilled-roles': [],
      '/api/vacancies/options': OPTIONS,
    });
    const { container } = renderApp(<VacanciesPage />);
    await waitFor(() => expect(container.querySelector('nldd-link')).not.toBeNull());
    const table = container.querySelector('nldd-table')!;
    // One track list for all rows: that is what aligns the columns.
    expect(table.getAttribute('columns')).toBe('minmax(240px,2fr) 150px minmax(240px,1.4fr) 150px');
    const header = [...table.querySelectorAll('nldd-table-row[slot="header"] nldd-text-cell')];
    expect(header.map((cell) => cell.getAttribute('text'))).toEqual([
      'Vacature',
      'Type',
      'Volgende stap',
      'Status',
    ]);
    const row = table.querySelector('nldd-table-row:not([slot])')!;
    const link = row.querySelector('nldd-link')!;
    expect(link.getAttribute('href')).toBe('/vacatures/v-1');
    expect(link.getAttribute('text')).toBe('Backend-ontwikkelaar');
    expect(row.textContent).toContain('Opdracht Alfa · Schaal 11, 0,8 fte');
    // The next step in the words of the step bar, with what it waits on and how long.
    const step = row.querySelector('nldd-text-cell[hide-below="md"][supporting-text]')!;
    expect(step.getAttribute('text')).toBe('Advies en akkoord');
    expect(step.getAttribute('supporting-text')).toMatch(/^Wacht op advies HR, al /);
    // The status is a word next to its color, once per width.
    const badge = row.querySelector('nldd-badge')!;
    expect(badge.getAttribute('text')).toBe('Aangevraagd');
    expect(badge.getAttribute('color')).toBe('accent');
    expect(row.querySelector('nldd-text-cell[hide-above="sm"]')?.getAttribute('overline')).toBe(
      'Aangevraagd',
    );
    expect(row.textContent).not.toContain('Laatste stap');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Vacatures');
  });

  it('offers a new vacancy only to who may create one', async () => {
    stubApi({
      '/api/vacancies': [],
      '/api/vacancies/unfilled-roles': [],
      '/api/vacancies/options': OPTIONS,
    });
    const { container, unmount } = renderApp(<VacanciesPage />);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(container.querySelector('nldd-button[text="Nieuwe vacature"]')).toBeNull();
    expect(container.querySelector('nldd-button[text="Formulier en taalmodel"]')).toBeNull();
    // Open roles are a view of this page: a choice in the bar, not a button.
    expect(container.querySelector('nldd-button[text="Open rollen"]')).toBeNull();
    expect(
      [...container.querySelectorAll('nldd-dropdown option')].map((option) => option.textContent),
    ).toContain('Open rollen');
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
    // The settings are under Beheer; the bar holds one derived list and the action.
    expect(second.container.querySelector('nldd-button[text="Formulier en taalmodel"]')).toBeNull();
    expect(second.container.querySelector('nldd-button[text="Standaardteksten"]')).toBeNull();
    // Open roles are a view of this page, chosen in the bar, not a link beside it.
    expect(second.container.querySelector('nldd-button[text="Open rollen"]')).toBeNull();
  });

  it('shows an error when the list cannot be loaded', async () => {
    stubApi({ '/api/vacancies/options': OPTIONS, '/api/vacancies/unfilled-roles': [] });
    const { container } = renderApp(<VacanciesPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-banner[variant="critical"]')).not.toBeNull(),
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
    expect(
      container.querySelector('nldd-title[text="Productmanager"]')?.getAttribute('supporting-text'),
    ).toBe('Schaal 13, 1 fte');
    // A view of the Vacatures page: the same title, no link back.
    expect(container.querySelector('nldd-link[text="Terug naar Vacatures"]')).toBeNull();
    expect(container.querySelector('h1')?.textContent).toBe('Vacatures');
    expect(container.textContent).toContain('Geplaatst op');
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
