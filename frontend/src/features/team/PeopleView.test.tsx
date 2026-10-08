import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { TeamPage } from './TeamPage';
import { mockApi, texts } from './ui/testing';

const ROSTER = {
  id: 'p-1',
  name: 'Rik Medewerker',
  email: 'rik@example.org',
  is_active: true,
  manager_id: null,
  manager_name: null,
};

afterEach(() => vi.unstubAllGlobals());

async function renderPeople(items: object[], mayManage = false) {
  mockApi({
    '/api/people': {
      items,
      may_manage: mayManage,
      period_start: '2026-06-01',
      period_end: '2026-06-01',
    },
  });
  const view = renderApp(<TeamPage />, { path: '/team' });
  await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
  return view.container;
}

function headers(container: HTMLElement): string[] {
  return texts(container, 'nldd-table-row[slot="header"] nldd-text-cell');
}

describe('PeopleView', () => {
  it('draws no column for data the asker may not see', async () => {
    const container = await renderPeople([ROSTER]);
    expect(headers(container)).toEqual(['Naam', 'Leidinggevende', 'Actie']);
    expect(texts(container, 'nldd-button')).not.toContain('Persoon toevoegen');
  });

  it('draws the staffing column for a planner, without amounts', async () => {
    const container = await renderPeople([{ ...ROSTER, functions: ['planner'], is_hired: false }]);
    expect(headers(container)).toEqual(['Naam', 'Leidinggevende', 'Functies', 'Actie']);
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain('Planner');
  });

  it('draws rate and cost columns when at least one person carries them', async () => {
    const container = await renderPeople(
      [
        {
          ...ROSTER,
          functions: [],
          is_hired: true,
          billing_scale: 14,
          rate_category: 'D',
          monthly_rate_cents: 1800000,
          scales: [],
          cost_monthly_rate_cents: 1500000,
          margin_monthly_cents: 300000,
          hires: [],
        },
        { ...ROSTER, id: 'p-2', name: 'Otto Overig' },
      ],
      true,
    );
    expect(headers(container)).toEqual([
      'Naam',
      'Leidinggevende',
      'Functies',
      'Inzetschaal',
      'Categorie',
      'Maandtarief',
      'Kostprijs inhuur',
      'Marge per maand',
      'Actie',
    ]);
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells.some((text) => text.includes('18.000'))).toBe(true);
    expect(cells.some((text) => text.includes('3.000'))).toBe(true);
    expect(texts(container, 'nldd-button')).toContain('Persoon toevoegen');
  });

  it('asks for the people of one reference day', async () => {
    const { calls } = mockApi({
      '/api/people': { items: [], may_manage: false, period_start: '', period_end: '' },
    });
    renderApp(<TeamPage />, { path: '/team' });
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    const url = new URL(calls[0] ?? '', 'http://test');
    expect(url.searchParams.get('period_start')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(url.searchParams.get('period_start')).toBe(url.searchParams.get('period_end'));
  });

  it('explains an empty list', async () => {
    const container = await renderPeople([]);
    expect(texts(container, 'nldd-inline-dialog[slot="empty"]')).toEqual([
      'Er zijn geen personen om te tonen',
    ]);
  });
});
