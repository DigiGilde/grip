import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { mockApi, texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import type { TemplateDetail } from './api';
import { FormTemplatePage } from './FormTemplatePage';

const DETAIL: TemplateDetail = {
  id: 'f-1',
  name: 'Aanvraagformulier vacature',
  file_name: 'formulier.pdf',
  is_active: true,
  fields: [
    {
      name: 'Text1',
      type: 'text',
      label: 'Vacatureaanvrager',
      source: 'requester_name',
      fills: 'Naam van de aanvrager',
      state: 'mapped',
    },
    {
      name: 'Selectievakje 16',
      type: 'checkbox',
      label: 'Declarabele vacature: Ja',
      source: 'declarable',
      equals: true,
      fills: 'Of de vacature declarabel is: aangevinkt bij ja',
      state: 'mapped',
    },
    { name: 'Text99', type: 'text', state: 'unfilled' },
    {
      name: 'Weg',
      type: 'text',
      label: 'Oud veld',
      source: 'scale',
      fills: 'Schaal',
      state: 'missing',
    },
  ],
  sources: [
    { key: 'requester_name', label: 'Naam van de aanvrager', choices: [] },
    { key: 'scale', label: 'Schaal', choices: [] },
    {
      key: 'declarable',
      label: 'Of de vacature declarabel is',
      choices: [
        { value: true, label: 'ja' },
        { value: false, label: 'nee' },
      ],
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

async function renderPage(vacancies: object[] = []) {
  mockApi({ '/api/form-templates/f-1': DETAIL, '/api/vacancies': vacancies });
  const view = renderApp(
    <Routes>
      <Route path={PATHS.formTemplate} element={<FormTemplatePage />} />
    </Routes>,
    { path: '/vacatures/beheer/formulier/f-1' },
  );
  await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
  return view.container;
}

const href = (container: ParentNode, text: string) =>
  container.querySelector(`nldd-link[text="${text}"]`)?.getAttribute('href');

describe('FormTemplatePage', () => {
  it('names every field by its caption and says in words what fills it', async () => {
    const container = await renderPage();
    expect(texts(container, 'nldd-table nldd-link')).toEqual([
      'Vacatureaanvrager',
      'Declarabele vacature: Ja',
      'Text99',
      'Oud veld',
    ]);
    const filled = [...container.querySelectorAll('nldd-table nldd-text-cell')].map((cell) =>
      cell.getAttribute('text'),
    );
    expect(filled).toContain('Naam van de aanvrager');
    expect(filled).toContain('Of de vacature declarabel is: aangevinkt bij ja');
    // What nothing fills and what the form no longer has stand out.
    expect(texts(container, 'nldd-table nldd-badge')).toEqual([
      'Grip vult dit niet in',
      'Staat niet meer in het formulier',
    ]);
  });

  it('opens the blank form and a sample with example values when there is no vacancy', async () => {
    const container = await renderPage();
    expect(href(container, 'Bekijk het lege formulier')).toBe('/api/form-templates/f-1/file');
    expect(href(container, 'Bekijk een ingevuld voorbeeld')).toBe('/api/form-templates/f-1/sample');
  });

  it('fills the sample for the most recent vacancy by default', async () => {
    const container = await renderPage([
      { id: 'v-9', function_title: 'Voorbeeldfunctie', status: 'draft' },
      { id: 'v-1', function_title: 'Oudere functie', status: 'draft' },
    ]);
    await waitFor(() =>
      expect(href(container, 'Bekijk een ingevuld voorbeeld')).toBe(
        '/api/form-templates/f-1/sample?vacancy_id=v-9',
      ),
    );
    const options = [...container.querySelectorAll('nldd-dropdown option')].map(
      (option) => option.textContent,
    );
    expect(options).toEqual([
      'Vacature Voorbeeldfunctie',
      'Vacature Oudere functie',
      'Voorbeeldwaarden in elk veld',
    ]);
  });
});
