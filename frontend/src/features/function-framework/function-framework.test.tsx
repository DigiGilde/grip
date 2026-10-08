import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import type { Vacancy } from '@/features/vacancies/api';
import { budgetLineWarning, missingRequestDetails } from '@/features/vacancies/labels';
import { requestPrepared, vacancySteps } from '@/features/vacancies/steps';
import { VacanciesPage } from '@/features/vacancies/VacanciesPage';
import {
  groupChoices,
  parseScales,
  reloadSummary,
  scaleTag,
  searchGroups,
  suggestedFirst,
  type FunctionFramework,
} from './api';
import { FunctionFrameworkPage } from './FunctionFrameworkPage';

// Fictional entries in the shape of the real list.
const FRAMEWORK: FunctionFramework = {
  source: {
    name: 'Functiegebouw Rijk',
    source_url: 'https://bron.example/functiegebouw',
    read_on: '2026-10-08',
    reference_families: 2,
    reference_groups: 3,
  },
  families: [
    {
      id: 'f-1',
      name: 'Testadvisering',
      source: 'reference',
      groups: [
        {
          id: 'g-1',
          family_id: 'f-1',
          name: 'Testadviseur',
          scales: [11, 12, 13],
          scales_text: 'schaal 11 t/m 13',
          source: 'reference',
          edited: false,
        },
        {
          id: 'g-2',
          family_id: 'f-1',
          name: 'Testverzorger',
          scales: [12],
          scales_text: 'schaal 12',
          source: 'reference',
          edited: true,
        },
      ],
    },
    {
      id: 'f-2',
      name: 'Testuitvoering',
      source: 'reference',
      groups: [
        {
          id: 'g-3',
          family_id: 'f-2',
          name: 'Testmedewerker',
          scales: [5, 6, 7, 8],
          scales_text: 'schaal 5 t/m 8',
          source: 'manual',
          valid_to: '2026-09-30',
          edited: true,
        },
      ],
    },
  ],
  can_manage: true,
};

const OPTIONS = {
  vacancy_types: [{ value: 'regulier', label: 'Regulier' }],
  contract_types: [{ value: 'temporary_project', label: 'Tijdelijk (projectcontract)' }],
  statuses: [],
  channels: [],
  decision_kinds: [],
  text_kinds: [],
  steps: [],
  drafting_available: false,
  request_form_available: false,
  can_create_without_budget_line: true,
  can_manage_setup: false,
};

const VACANCY: Vacancy = {
  id: 'v-1',
  function_title: 'Backend-ontwikkelaar',
  fgr_function_name: 'Testadviseur',
  scale: 11,
  fte: '0.80',
  status: 'draft',
  declarable: true,
  vacancy_type: 'regulier',
  channels: [],
  assignment_name: 'Opdracht Alfa',
  has_openings: true,
  function_group_id: 'g-1',
  function_family_name: 'Testadvisering',
  function_group_scales: [11, 12, 13],
  suggested_function_group_ids: ['g-1', 'g-2'],
  budget_line_scales: [12, 13],
  scale_fits_budget_line: false,
  procedure: [],
  decisions: [],
  texts: [],
  requester_name: 'Fictieve Eigenaar',
  addressee_name: null,
  addressee_has_account: false,
  permissions: {
    can_edit: true,
    can_record_hr_advice: false,
    can_record_control_advice: false,
    can_record_approval: false,
    can_download_form: false,
  },
};

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
      return new Response(JSON.stringify({ title: 'Niet gevonden', status: 404 }), {
        status: 404,
        headers: { 'Content-Type': 'application/problem+json' },
      });
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('helpers', () => {
  const choices = groupChoices(FRAMEWORK);

  it('searches on group and family names', () => {
    expect(searchGroups(choices, 'adviseur').map((c) => c.id)).toEqual(['g-1']);
    expect(searchGroups(choices, 'testuitvoering').map((c) => c.id)).toEqual(['g-3']);
    expect(searchGroups(choices, 'test advisering').map((c) => c.id)).toEqual(['g-1', 'g-2']);
    expect(searchGroups(choices, '')).toHaveLength(3);
    expect(searchGroups(choices, 'bestaat niet')).toEqual([]);
  });

  it('puts groups that fit the scales first', () => {
    const { suggested, others } = suggestedFirst(choices, [12, 13]);
    expect(suggested.map((c) => c.id)).toEqual(['g-1', 'g-2']);
    expect(others.map((c) => c.id)).toEqual(['g-3']);
    expect(suggestedFirst(choices, null).suggested).toEqual([]);
  });

  it('reads scales as a list or a range', () => {
    expect(parseScales('11, 12, 13')).toEqual([11, 12, 13]);
    expect(parseScales('11-13')).toEqual([11, 12, 13]);
    expect(parseScales('13 11')).toEqual([11, 13]);
    expect(parseScales('')).toBeNull();
    expect(parseScales('20')).toBeNull();
    expect(parseScales('elf')).toBeNull();
  });

  it('warns when the scale is outside the budget line category', () => {
    expect(budgetLineWarning(12, [12, 13])).toBeNull();
    expect(budgetLineWarning(null, [12, 13])).toBeNull();
    expect(budgetLineWarning(14, null)).toBeNull();
    expect(budgetLineWarning(14, [12, 13])).toContain('te laag begroot');
    expect(budgetLineWarning(11, [12, 13])).toContain('te hoog begroot');
    expect(budgetLineWarning(11, [12, 13])).toContain('schaal 12 t/m 13');
  });

  it('lists what the request form still needs', () => {
    expect(missingRequestDetails({})).toEqual([
      'FGR-functienaam',
      'schaal',
      'type contract',
      'aan wie de aanvraag gericht is',
    ]);
    expect(
      missingRequestDetails({
        fgr_function_name: 'Testadviseur',
        scale: 12,
        contract_type: 'temporary_project',
        addressee_name: 'Fictief Directielid',
      }),
    ).toEqual([]);
  });
});

describe('the steps of a vacancy', () => {
  const prepared: Vacancy = {
    ...VACANCY,
    contract_type: 'temporary_project',
    addressee_name: 'Fictief Directielid',
  };

  it('starts at preparing the request and moves on when it is filled', () => {
    expect(requestPrepared(VACANCY)).toBe(false);
    expect(vacancySteps(VACANCY)).toMatchObject({ current: 1, action: 'prepare' });
    // The motivation is asked by the form but does not hold up the request.
    expect(requestPrepared(prepared)).toBe(true);
    expect(vacancySteps(prepared)).toMatchObject({ current: 2, action: 'submit' });
  });

  it('follows the procedure of the type', () => {
    expect(vacancySteps({ ...prepared, status: 'requested' })).toMatchObject({
      current: 3,
      action: 'decide',
    });
    expect(vacancySteps({ ...prepared, status: 'approved' })).toMatchObject({
      current: 4,
      action: 'open',
    });
    const ready: Vacancy = {
      ...prepared,
      status: 'approved',
      has_openings: false,
      permissions: { ...prepared.permissions, can_fill: true },
    };
    const steps = vacancySteps(ready)!;
    expect(steps.items).toEqual([
      'Aanvraag voorbereiden',
      'Aanvragen',
      'Advies en akkoord',
      'Vervullen',
    ]);
    expect(steps).toMatchObject({ current: 4, action: 'fill' });
    expect(vacancySteps({ ...prepared, status: 'open' })).toMatchObject({ current: 5 });
  });

  it('has no action for a reader who may not take it, and no steps once it ended', () => {
    const reader: Vacancy = {
      ...VACANCY,
      permissions: { ...VACANCY.permissions, can_edit: false },
    };
    expect(vacancySteps(reader)).toMatchObject({ current: 1, action: null });
    expect(vacancySteps({ ...VACANCY, status: 'filled' })).toBeNull();
    expect(vacancySteps({ ...VACANCY, status: 'withdrawn' })).toBeNull();
    expect(vacancySteps({ ...VACANCY, status: 'rejected' })).toBeNull();
  });
});

describe('creating a vacancy', () => {
  it('asks only for the role and the type', async () => {
    stubApi({
      '/api/vacancies': [],
      '/api/vacancies/unfilled-roles': [],
      '/api/vacancies/options': OPTIONS,
    });
    renderApp(<VacanciesPage />);
    await waitFor(() => expect(document.body.querySelector('nldd-sheet')).not.toBeNull());
    const sheet = document.body.querySelector('nldd-sheet')!;
    const labels = [...sheet.querySelectorAll('nldd-form-field')].map((el) =>
      el.getAttribute('label'),
    );
    expect(labels).toEqual(['Rol', 'Type vacature']);
    expect(sheet.textContent).toContain(
      'Functienaam, schaal, type contract en geadresseerde vul je hierna in.',
    );
  });
});

describe('FunctionFrameworkPage', () => {
  it('fits a screen: families closed with their count, no group until asked', async () => {
    stubApi({ '/api/function-framework': FRAMEWORK });
    const { container } = renderApp(<FunctionFrameworkPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-list[accessible-label="Functiefamilies"]')).not.toBeNull(),
    );
    const rows = [...container.querySelectorAll('nldd-list[accessible-label="Functiefamilies"] nldd-list-item')];
    expect(
      rows.map((row) => [...row.querySelectorAll('nldd-text-cell')].map((cell) => cell.getAttribute('text'))),
    ).toEqual([
      ['Testadvisering', '2 functiegroepen'],
      ['Testuitvoering', '1 functiegroep'],
    ]);
    expect(rows.every((row) => !row.hasAttribute('expanded'))).toBe(true);
    expect(container.querySelector('nldd-table')).toBeNull();
    expect(container.textContent).toContain('3 functiegroepen in 2 functiefamilies');
    expect(container.querySelector('a[href="https://bron.example/functiegebouw"]')).not.toBeNull();
    // One primary action; the reload is the quiet one next to it.
    const primary = container.querySelectorAll('nldd-button[appearance="primary"]');
    expect([...primary].map((button) => button.getAttribute('text'))).toEqual([
      'Voeg functiegroep toe',
    ]);
    expect(
      container.querySelector('nldd-button[text="Laad referentiebestand opnieuw"]'),
    ).not.toBeNull();
    expect(container.querySelector('nldd-search-field')).not.toBeNull();
  });

  it('shows no beheer actions to a reader who may not manage the list', async () => {
    stubApi({ '/api/function-framework': { ...FRAMEWORK, can_manage: false } });
    const { container } = renderApp(<FunctionFrameworkPage />);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(container.querySelector('nldd-button')).toBeNull();
    expect(document.body.querySelector('nldd-sheet')).toBeNull();
  });

  it('writes scales as a compact tag and a reload as one line', () => {
    const [adviser, single] = groupChoices(FRAMEWORK);
    expect(scaleTag(adviser!)).toBe('11 t/m 13');
    expect(scaleTag(single!)).toBe('12');
    expect(
      reloadSummary({
        families_created: 0,
        families_updated: 0,
        groups_created: 0,
        groups_updated: 0,
        groups_kept: 1,
      }),
    ).toBe('Opnieuw geladen: gelijk aan het referentiebestand. 1 met de hand gewijzigd en zo gelaten.');
    expect(
      reloadSummary({
        families_created: 0,
        families_updated: 0,
        groups_created: 2,
        groups_updated: 1,
        groups_kept: 0,
      }),
    ).toBe('Opnieuw geladen: 2 toegevoegd, 1 bijgewerkt.');
  });
});
