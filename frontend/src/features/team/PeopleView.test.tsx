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

async function renderPeople(items: object[], mayManage = false, board?: object) {
  mockApi({
    ...(board ? { '/api/allocations/board': board } : {}),
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
    // Nobody in this list has a manager named, so that column is not drawn either.
    expect(headers(container)).toEqual(['Naam']);
    expect(texts(container, 'nldd-button')).toEqual([]);
    expect(container.querySelector('nldd-progress-bar')).toBeNull();
  });

  it('shows how much each person works now, and who needs attention first', async () => {
    const staffed = { functions: [], is_hired: false };
    const container = await renderPeople(
      [
        { ...ROSTER, ...staffed, current_assignment_count: 1, current_fte_pct: '100.000' },
        {
          ...ROSTER,
          ...staffed,
          id: 'p-2',
          name: 'Otto Over',
          current_assignment_count: 2,
          current_fte_pct: '120.000',
        },
        {
          ...ROSTER,
          ...staffed,
          id: 'p-3',
          name: 'Eva Einde',
          current_assignment_count: 1,
          current_fte_pct: '80.000',
        },
      ],
      false,
      {
        months: [],
        current_month: '2026-06-01',
        open_roles: [],
        can_add: false,
        persons: [
          { person_id: 'p-1', person_name: 'Rik Medewerker', cells: [], bars: [] },
          {
            person_id: 'p-2',
            person_name: 'Otto Over',
            cells: [],
            bars: [],
            over_months: ['2026-06-01'],
          },
          {
            person_id: 'p-3',
            person_name: 'Eva Einde',
            cells: [],
            bars: [],
            idle_from: '2026-09-01',
          },
        ],
      },
    );
    expect(headers(container)).toEqual(['Naam', 'Inzet nu', 'Vooruit']);
    await waitFor(() => expect(container.textContent).toContain('Boven 100% in jun'));
    expect(texts(container, 'nldd-table nldd-link')).toEqual([
      'Otto Over',
      'Eva Einde',
      'Rik Medewerker',
    ]);
    expect(container.textContent).toContain('Geen inzet vanaf september 2026');
    expect(texts(container, 'nldd-progress-bar')).toEqual(['120%', '80%', '100%']);
    expect(document.body.innerHTML).not.toContain('€');
  });

  it('draws scale and rate when at least one person carries them, and no cost', async () => {
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
    expect(headers(container)).toEqual(['Naam', 'Schaal', 'Maandtarief']);
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells.some((text) => text.includes('18.000'))).toBe(true);
    // What a hire costs is on the person's own page, not in a list.
    expect(cells.some((text) => text.includes('15.000'))).toBe(false);
    const actions = [...container.querySelectorAll('nldd-button')];
    expect(actions.map((el) => el.getAttribute('text'))).toEqual([
      'Voorstellen uit Wies',
      'Nieuwe persoon',
    ]);
    expect(actions.filter((el) => el.getAttribute('appearance') === 'primary')).toHaveLength(1);
  });

  it('asks for the people of today', async () => {
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
