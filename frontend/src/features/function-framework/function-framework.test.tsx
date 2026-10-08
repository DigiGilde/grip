import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { renderApp } from '@/test/utils';
import type { Vacancy } from '@/features/vacancies/api';
import { budgetLineWarning, missingRequestDetails } from '@/features/vacancies/labels';
import { requestPrepared, vacancySteps } from '@/features/vacancies/steps';
import { VacanciesPage } from '@/features/vacancies/VacanciesPage';
import { VacancyDetailPage } from '@/features/vacancies/VacancyDetailPage';
import {
  groupChoices,
  parseScales,
  searchGroups,
  suggestedFirst,
  type FunctionFramework,
} from './api';
import { FunctionFrameworkSection } from './FunctionFrameworkSection';

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

describe('preparing the request', () => {
  function renderDetail() {
    stubApi({
      '/api/vacancies/v-1': VACANCY,
      '/api/vacancies/options': OPTIONS,
      '/api/function-framework': FRAMEWORK,
      '/api/person-options': {
        items: [{ id: 'p-9', name: 'Fictief Directielid' }],
      },
    });
    return renderApp(
      <Routes>
        <Route path={PATHS.vacancyDetail} element={<VacancyDetailPage />} />
      </Routes>,
      { path: '/vacatures/v-1' },
    );
  }

  it('shows the family, the warning and what is still missing', async () => {
    const { container } = renderDetail();
    await waitFor(() =>
      expect(container.querySelector('nldd-text-cell[overline="FGR-functienaam"]')).not.toBeNull(),
    );
    expect(
      container
        .querySelector('nldd-text-cell[overline="FGR-functienaam"]')
        ?.getAttribute('supporting-text'),
    ).toBe('Functiefamilie Testadvisering');
    expect(
      container.querySelector('nldd-banner[variant="warning"]')?.getAttribute('text'),
    ).toContain('Schaal 11 valt buiten de tariefcategorie van de begrotingsregel');
    // The next step is unmistakable: step 1 is current and carries the primary button.
    expect(container.querySelector('nldd-step-bar')?.getAttribute('current')).toBe('1');
    const steps = [...container.querySelectorAll('nldd-step-bar-item')].map((el) =>
      el.getAttribute('text'),
    );
    expect(steps).toEqual([
      'Aanvraag voorbereiden',
      'Aanvragen',
      'Advies en akkoord',
      'Openstellen',
      'Vervullen',
    ]);
    const primary = container.querySelector('nldd-button[appearance="primary"]');
    expect(primary?.getAttribute('text')).toBe('Bereid aanvraag voor');
    // The checklist: ticked when filled, each line the way to fill it.
    const checklist = container.querySelector(
      'nldd-list[accessible-label="Voor het aanvraagformulier, nog 2 in te vullen"]',
    )!;
    const lines = [...checklist.querySelectorAll('nldd-list-item')].map((row) => ({
      label: row.querySelector('nldd-text-cell')?.getAttribute('text'),
      state: row.querySelector('nldd-text-cell')?.getAttribute('supporting-text'),
      icon: row.querySelector('nldd-icon-cell')?.getAttribute('icon'),
      button: row.hasAttribute('button'),
    }));
    expect(lines).toEqual([
      { label: 'FGR-functienaam', state: 'Testadviseur', icon: 'check-circle-filled', button: true },
      { label: 'Schaal', state: '11', icon: 'check-circle-filled', button: true },
      { label: 'Type contract', state: 'Nog niet ingevuld', icon: 'circle', button: true },
      { label: 'Aan', state: 'Nog niet ingevuld', icon: 'circle', button: true },
      {
        label: 'Aanleiding en motivatie',
        state: 'Nog open; kan ook na de aanvraag',
        icon: 'circle',
        button: true,
      },
    ]);
    // The details show the same fields, filled or visibly not.
    const fact = (label: string) =>
      container.querySelector(`nldd-text-cell[overline="${label}"]`)?.getAttribute('text');
    expect(fact('Schaal')).toBe('11');
    expect(fact('Type contract')).toBe('Nog niet ingevuld');
    expect(fact('Aan')).toBe('Nog niet ingevuld');
  });

  it('offers the function groups to search, and narrows the scale to the group', async () => {
    const { container } = renderDetail();
    await waitFor(() =>
      expect(container.querySelector('nldd-button[text="Bereid aanvraag voor"]')).not.toBeNull(),
    );
    // The sheets are in the document while closed; the lists load when one opens.
    const sheets = [...document.body.querySelectorAll('nldd-sheet')];
    const prepare = sheets.find((sheet) =>
      sheet.querySelector('nldd-top-title-bar')?.getAttribute('text')?.includes('voorbereiden'),
    )!;
    expect(prepare).toBeDefined();
    const combo = prepare.querySelector('nldd-combo-box')!;
    expect(combo.getAttribute('value')).toBe('g-1');
    // The scale is a choice from the scales of the group once the list is known;
    // until then it is a plain field. Either way no free FGR text field.
    const labels = [...prepare.querySelectorAll('nldd-form-field')].map((el) =>
      el.getAttribute('label'),
    );
    expect(labels[0]).toBe('FGR-functienaam');
    expect(labels).toContain('Schaal');
    expect(labels).toContain('Type contract');
    expect(prepare.querySelector('nldd-checkbox-field[label="De functiegroep staat niet in de lijst"]')).not.toBeNull();
  });
});

describe('FunctionFrameworkSection', () => {
  it('lists families and groups with their scales and where they come from', async () => {
    stubApi({ '/api/function-framework': FRAMEWORK });
    const { container } = renderApp(<FunctionFrameworkSection />);
    await waitFor(() =>
      expect(container.querySelector('nldd-title[text="Testadvisering"]')).not.toBeNull(),
    );
    const line = (name: string) =>
      container.querySelector(`nldd-text-cell[text="${name}"]`)?.getAttribute('supporting-text');
    expect(line('Testadviseur')).toBe('schaal 11 t/m 13');
    expect(line('Testverzorger')).toBe('schaal 12 · met de hand gewijzigd');
    expect(line('Testmedewerker')).toContain('zelf toegevoegd');
    expect(line('Testmedewerker')).toContain('beëindigd per');
    expect(container.textContent).toContain('3 functiegroepen in 2 functiefamilies');
    expect(container.querySelector('a[href="https://bron.example/functiegebouw"]')).not.toBeNull();
    expect(container.querySelector('nldd-button[text="Voeg functiegroep toe"]')).not.toBeNull();
    expect(
      container.querySelector('nldd-button[text="Laad referentiebestand opnieuw"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('nldd-button[accessible-label="Wijzig de functiegroep Testadviseur"]'),
    ).not.toBeNull();
  });
});
