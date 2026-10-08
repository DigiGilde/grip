import { fireEvent, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp, TEST_PERSON } from '@/test/utils';
import { PersonPage } from './PersonPage';
import { bar, board as boardOf, cells } from '@/features/allocations/board/testing';
import { texts } from './ui/testing';

const ROSTER = {
  id: 'p-1',
  name: 'Rik Medewerker',
  email: 'rik@example.org',
  is_active: true,
  stage: 'colleague',
  starts_on: null,
  manager_id: null,
  manager_name: 'Lies Leidinggevende',
};
const STAFFING = {
  functions: ['planner'],
  function_grants: [{ function: 'planner', since: '2026-03-01', granted_by_name: 'Bea Beheerder' }],
  is_sole_beheerder: false,
  is_hired: false,
  current_assignment_count: 2,
  current_fte_pct: '80.000',
  hires: [],
};
const RATE = {
  billing_scale: 14,
  rate_category: 'D',
  monthly_rate_cents: 1800000,
  scales: [{ id: 's-1', valid_from: '2026-01-01', valid_to: null, billing_scale: 14 }],
};
const KPI = {
  person_id: 'p-1',
  person_name: 'Rik Medewerker',
  year: 2026,
  target_pct: '90.00',
  target_cents: 19440000,
  realised_cents: 1800000,
  forecast_cents: 19800000,
  realisation_cents: 21600000,
  unavailable_reason: null,
};

afterEach(() => vi.unstubAllGlobals());

interface Mock {
  person: object;
  kpi?: object;
  loginBound?: boolean;
  roles?: object[];
  impact?: object;
  outgoing?: object[];
  board?: object;
}

function mock({ person, kpi, loginBound, roles, impact, outgoing, board }: Mock) {
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      calls.push({ method, url });
      const path = url.split('?')[0] ?? url;
      let body: unknown = null;
      if (path === '/api/people/p-1') body = person;
      else if (path === '/api/kpi/p-1' && kpi) body = kpi;
      else if (path === '/api/allocations/board' && board) body = board;
      else if (path === '/api/people/p-1/login')
        body = { bound: method === 'DELETE' ? false : Boolean(loginBound) };
      else if (path.startsWith('/api/people/p-1/functions/')) body = person;
      else if (path === '/api/people/p-1/roles' && roles) body = { person_id: 'p-1', items: roles };
      else if (path === '/api/people/p-1/scales/preview' && impact) body = impact;
      else if (path === '/api/integrations/wies/reconciliation' && outgoing)
        body = { configured: true, proposals: [], outgoing };
      const status = body === null ? 404 : 200;
      return Promise.resolve(
        new Response(JSON.stringify(body ?? { title: 'Niet gevonden', status: 404 }), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
  return calls;
}

async function renderPerson(options: Mock, functions: string[] = []) {
  const calls = mock(options);
  const view = renderApp(
    <Routes>
      <Route path="/team/:personId" element={<PersonPage />} />
    </Routes>,
    {
      path: '/team/p-1?peildatum=2026-06-01',
      auth: { status: 'authenticated', person: TEST_PERSON, functions },
    },
  );
  await waitFor(() => expect(view.container.querySelector('nldd-tag')).not.toBeNull());
  return { container: view.container, calls };
}

const sections = (container: HTMLElement) => texts(container, 'nldd-title[heading-level="2"]');
const buttons = (root: ParentNode) => texts(root, 'nldd-button');
const button = (root: ParentNode, text: string) =>
  [...root.querySelectorAll('nldd-button')].find((el) => el.getAttribute('text') === text);
const menuItems = (root: ParentNode) => texts(root, 'nldd-menu-item');
/** Chooses an item of a menu, as the design system reports it. */
function choose(root: ParentNode, text: string) {
  const item = [...root.querySelectorAll('nldd-menu-item')].find(
    (el) => el.getAttribute('text') === text,
  );
  expect(item).toBeDefined();
  fireEvent(item as Element, new CustomEvent('select'));
}
const identity = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-container[slot="header"] nldd-container > *')].map(
    (el) => el.getAttribute('text') ?? el.textContent ?? '',
  );
const sheetOf = (title: string) =>
  document.body
    .querySelector(`nldd-top-title-bar[text="${title}"]`)
    ?.closest('nldd-sheet') as HTMLElement;

const BOARD = boardOf({
  persons: [
    {
      person_id: 'p-1',
      person_name: 'Rik Medewerker',
      cells: cells([50, 50, 80, 80, 80, 80, 30, 30, 30, 0, 0, 0]),
      now_pct: '80',
      room_from: '2026-07-01',
      idle_from: '2026-10-01',
      over_months: [],
      bars: [
        bar({ allocation_id: 'x1', person_id: 'p-1', fte_pct: '50.00', closed_months: [] }),
        bar({
          allocation_id: 'x2',
          person_id: 'p-1',
          assignment_id: 'a2',
          assignment_name: 'Opdracht Beta',
          role: 'Analist',
          start_date: '2026-03-01',
          end_date: '2026-09-30',
          fte_pct: '30.00',
          closed_months: [],
        }),
      ],
    },
  ],
});

describe('what each reader sees of a person', () => {
  it('shows a team member only who a colleague is', async () => {
    const { container } = await renderPerson({ person: ROSTER });
    expect(container.querySelector('h1')?.textContent).toBe('Rik Medewerker');
    expect(identity(container)).toEqual([
      'Collega',
      'rik@example.org',
      'Leidinggevende: Lies Leidinggevende',
    ]);
    expect(sections(container)).toEqual([]);
    // No section, field or action for anything else is in the document.
    const html = document.body.innerHTML;
    for (const word of ['Inzet', 'Schaal', 'Kostprijs', 'Declarabiliteit', 'Rechten in grip']) {
      expect(html).not.toContain(word);
    }
    expect(buttons(document.body)).toEqual([]);
    expect(menuItems(document.body)).toEqual([]);
  });

  it('gives a planner the deployment and the roles, without amounts or actions', async () => {
    const { container, calls } = await renderPerson({
      person: { ...ROSTER, ...STAFFING },
      board: BOARD,
      roles: [
        { role_id: 'r-1', name: 'Developer', source: 'wies', is_active: true },
        { role_id: 'r-2', name: 'Productmanager', source: 'manual', is_active: true },
        { role_id: 'r-3', name: 'Tester', source: 'manual', is_active: false },
      ],
    });
    await waitFor(() => expect(container.querySelector('.grip-board')).not.toBeNull());
    await waitFor(() => expect(identity(container)).toContain('Developer, Productmanager'));
    expect(sections(container)).toEqual(['Inzet', 'Rechten in grip']);
    expect(identity(container)[0]).toBe('In dienst');
    expect(container.textContent).toContain('Nu 80% op 2 opdrachten');
    expect(container.textContent).toContain('Laatste inzet eindigt op 30 sep 2026');
    expect(container.textContent).toContain('Geen inzet vanaf oktober 2026');
    // Every assignment is a link, and the board is one step away.
    expect(container.querySelector('nldd-link[href="/opdrachten/a2/bemensing"]')).not.toBeNull();
    expect(container.querySelector('nldd-link[href="/inzet?persoon=p-1"]')).not.toBeNull();
    expect(document.body.innerHTML).not.toContain('€');
    expect(buttons(document.body)).toEqual([]);
    expect(menuItems(document.body)).toEqual([]);
    expect(calls.filter((call) => call.url.endsWith('/login'))).toEqual([]);
  });

  it('gives a line manager, and the person themselves, scale and KPI but no cost', async () => {
    const { container } = await renderPerson({
      person: { ...ROSTER, ...STAFFING, ...RATE },
      kpi: KPI,
    });
    await waitFor(() => expect(sections(container)).toContain('Declarabiliteit 2026'));
    expect(sections(container)).toEqual([
      'Inzet',
      'Declarabiliteit 2026',
      'Inzetschaal',
      'Rechten in grip',
    ]);
    expect(identity(container)).toContain('Schaal 14');
    expect(document.body.innerHTML).not.toContain('Kostprijs');
    expect(document.body.innerHTML).not.toContain('Marge');
    expect(buttons(document.body)).toEqual([]);
  });

  it('shows a hire as periods, with the cost only when it is there', async () => {
    const hired = {
      ...ROSTER,
      ...STAFFING,
      is_hired: true,
      hires: [
        {
          id: 'h-1',
          supplier: 'Voorbeeld Detachering',
          valid_from: '2026-01-01',
          valid_to: '2026-12-31',
          contract_reference: 'VD-26-014',
        },
      ],
    };
    const { container } = await renderPerson({ person: hired });
    expect(identity(container)[0]).toBe('Ingehuurd via Voorbeeld Detachering');
    expect(sections(container)).toContain('Inhuur');
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain('1 jan 2026 t/m 31 dec 2026');
    expect(document.body.innerHTML).not.toContain('Kostprijs');

    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    const withCost = await renderPerson({
      person: {
        ...hired,
        hires: [{ ...hired.hires[0], cost_monthly_rate_cents: 1500000 }],
        cost_monthly_rate_cents: 1500000,
        margin_monthly_cents: 300000,
      },
    });
    const cellsWithCost = texts(withCost.container, 'nldd-table nldd-text-cell');
    expect(cellsWithCost).toContain('Kostprijs per FTE per maand');
    expect(withCost.container.textContent).toContain('3.000');
  });

  it('says nothing about hiring for someone who is not hired', async () => {
    const { container } = await renderPerson({ person: { ...ROSTER, ...STAFFING } }, ['planner']);
    const html = container.innerHTML.toLowerCase();
    expect(html).not.toContain('inhuur');
    expect(html).not.toContain('ingehuurd');
  });

  it('reads a prospective colleague as one at a glance', async () => {
    const { container } = await renderPerson({
      person: { ...ROSTER, email: null, stage: 'prospective', starts_on: '2026-09-01' },
    });
    expect(identity(container)[0]).toBe('Aanstaande collega, start op 1 sep 2026');
  });

  it('answers not found for a person the reader may not see', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ title: 'Niet gevonden', status: 404 }), {
            status: 404,
            headers: { 'Content-Type': 'application/problem+json' },
          }),
        ),
      ),
    );
    const { container } = renderApp(
      <Routes>
        <Route path="/team/:personId" element={<PersonPage />} />
      </Routes>,
      { path: '/team/p-1' },
    );
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toEqual(['Deze persoon is niet gevonden']),
    );
  });
});

describe('how a person is doing', () => {
  it('draws the deployment as a bar per assignment over the months', async () => {
    const { container } = await renderPerson({ person: { ...ROSTER, ...STAFFING }, board: BOARD });
    await waitFor(() => expect(container.querySelector('.grip-board')).not.toBeNull());
    const bars = [...container.querySelectorAll('.grip-board__bar-label')].map((el) =>
      (el.textContent ?? '').trim(),
    );
    expect(bars).toEqual(['50% Opdracht Alfa', '30% Opdracht Beta']);
    expect(container.querySelector('.grip-board th[scope="row"]')?.textContent).toContain(
      'Alle opdrachten',
    );
  });

  it('says the declarability as one figure against the target', async () => {
    const { container } = await renderPerson({ person: { ...ROSTER, ...STAFFING }, kpi: KPI });
    await waitFor(() => expect(sections(container)).toContain('Declarabiliteit 2026'));
    const figure = container.querySelector('nldd-title[overline="Verwacht totaal"]');
    expect((figure?.getAttribute('text') ?? '').replace(/\u00a0/g, ' ')).toBe('€ 216.000');
    expect((figure?.getAttribute('supporting-text') ?? '').replace(/\u00a0/g, ' ')).toBe(
      'Target € 194.400, 90% van het jaar',
    );
    expect(texts(container, 'nldd-tag')).toContain('Haalt het target');
    const segments = [...container.querySelectorAll('nldd-progress-bar-segment-indicator')].map(
      (el) => [el.getAttribute('name'), el.getAttribute('value')],
    );
    expect(segments).toEqual([
      ['Gerealiseerd', '1800000'],
      ['Nog gepland', '19800000'],
    ]);
  });

  it('says so when the expected total stays under the target', async () => {
    const { container } = await renderPerson({
      person: { ...ROSTER, ...STAFFING },
      kpi: { ...KPI, forecast_cents: 10000000, realisation_cents: 11800000 },
    });
    await waitFor(() => expect(texts(container, 'nldd-tag')).toContain('Blijft onder het target'));
  });

  it('reads a promotion as a step, with the earlier period under it', async () => {
    const { container } = await renderPerson({
      person: {
        ...ROSTER,
        ...STAFFING,
        billing_scale: 12,
        rate_category: 'C',
        monthly_rate_cents: 1500000,
        scales: [
          { id: 's-1', valid_from: '2025-01-01', valid_to: '2026-04-30', billing_scale: 11 },
          { id: 's-2', valid_from: '2026-05-01', valid_to: null, billing_scale: 12 },
        ],
      },
    });
    const table = container.querySelector(
      'nldd-table[accessible-label="Inzetschaal van Rik Medewerker"]',
    ) as HTMLElement;
    const rows = texts(table, 'nldd-text-cell');
    expect(rows).toContain('Schaal 12, was 11');
    expect(rows).toContain('Schaal 11');
    expect(rows).toContain('1 jan 2025 t/m 30 apr 2026');
    expect(texts(table, 'nldd-badge')).toEqual(['Geldt nu']);
  });
});

describe('what the beheerder can do', () => {
  const FULL = { ...ROSTER, ...STAFFING, ...RATE };

  it('has one action: a menu of what can change, named as events', async () => {
    const { container } = await renderPerson({ person: FULL, kpi: KPI, loginBound: true }, [
      'beheerder',
    ]);
    await waitFor(() => expect(sections(container)).toContain('Declarabiliteit 2026'));
    await waitFor(() => expect(menuItems(container)).toContain('Ontkoppel de login'));
    expect(document.body.querySelectorAll('form')).toHaveLength(0);
    expect(buttons(container)).toEqual(['Leg een verandering vast']);
    expect(button(container, 'Leg een verandering vast')).toHaveAttribute('appearance', 'primary');
    expect(texts(container, 'nldd-menu-group')).toEqual(['Werk', 'Toegang', 'Gegevens']);
    expect(
      menuItems(container.querySelector('nldd-container[slot="header"]') as HTMLElement),
    ).toEqual([
      'Promotie of andere schaal',
      'Andere leidinggevende',
      'Andere rollen',
      'Wordt ingehuurd',
      'Target declarabel 2026',
      'Krijgt een recht in grip',
      'Ontkoppel de login',
      'Naam of e-mailadres',
      'Vertrekt of wordt inactief',
    ]);
  });

  it('shows what a promotion changes before it is saved', async () => {
    const { container, calls } = await renderPerson(
      {
        person: FULL,
        impact: {
          budget_lines_changed: 0,
          budget_difference_cents: 0,
          allocations_changed: 2,
          open_difference_cents: 90000,
          closed_difference_cents: 0,
          correction_cents: 30000,
          unpriced_months: 0,
          reaches_into_the_past: true,
          assignments: [],
        },
      },
      ['beheerder'],
    );
    choose(container, 'Promotie of andere schaal');
    const sheet = sheetOf('Promotie of andere schaal van Rik Medewerker');
    await waitFor(() => expect(sheet.querySelector('form')).not.toBeNull());
    // Nothing is asked before there is a scale to ask about.
    expect(calls.some((call) => call.url.includes('/scales/preview'))).toBe(false);
    const scale = sheet.querySelectorAll('nldd-text-field')[0] as HTMLElement;
    fireEvent(scale, new CustomEvent('input', { detail: { value: '15' } }));
    await waitFor(() => expect(sheet.querySelectorAll('nldd-text').length).toBeGreaterThan(1));
    const sentences = [...sheet.querySelectorAll('nldd-text')].map((el) =>
      (el.textContent ?? '').replace(/\u00a0/g, ' '),
    );
    expect(sentences.some((text) => text.startsWith('2 inzetten krijgen vanaf 1 jun 2026'))).toBe(
      true,
    );
    expect(sentences.some((text) => text.includes('naverrekening van samen € 300 hoger'))).toBe(
      true,
    );
    // Looking saved nothing.
    expect(calls.filter((call) => call.method === 'POST' && call.url.endsWith('/scales'))).toEqual(
      [],
    );
  });

  it('shows since when and by whom a right was granted', async () => {
    const { container } = await renderPerson({ person: FULL }, ['beheerder']);
    const rights = texts(container, 'nldd-table nldd-text-cell');
    expect(rights).toContain('Planner');
    expect(rights).toContain('Sinds 1 mrt 2026, toegekend door Bea Beheerder');
  });

  it('revokes a right from its row, only after a confirmation', async () => {
    const { container, calls } = await renderPerson({ person: FULL }, ['beheerder']);
    choose(container, 'Trek in');
    const dialog = [...document.body.querySelectorAll('nldd-modal-dialog')].find((el) =>
      el.getAttribute('text')?.includes('intrekken'),
    ) as HTMLElement;
    expect(dialog.getAttribute('text')).toBe('Het recht Planner van Rik Medewerker intrekken?');
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false);

    fireEvent.click(button(dialog, 'Trek in') as Element);
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: 'DELETE',
        url: '/api/people/p-1/functions/planner',
      }),
    );
  });

  it('keeps the only beheerder a beheerder and active', async () => {
    const sole = {
      ...FULL,
      functions: ['beheerder'],
      function_grants: [{ function: 'beheerder', since: '2026-01-05', granted_by_name: null }],
      is_sole_beheerder: true,
    };
    const { container } = await renderPerson({ person: sole }, ['beheerder']);
    expect(menuItems(container)).not.toContain('Trek in');
    expect(menuItems(container)).not.toContain('Vertrekt of wordt inactief');
    const rights = [...container.querySelectorAll('nldd-table nldd-text-cell')];
    expect(rights.some((cell) => cell.getAttribute('text')?.includes('bij de inrichting'))).toBe(
      true,
    );
    expect(
      rights.some((cell) => cell.getAttribute('supporting-text')?.includes('enige beheerder')),
    ).toBe(true);
  });

  it('asks for confirmation before granting a right that reaches far', async () => {
    const { container, calls } = await renderPerson({ person: FULL }, ['beheerder']);
    choose(container, 'Krijgt een recht in grip');
    const sheet = sheetOf('Recht toekennen aan Rik Medewerker');
    await waitFor(() => expect(sheet.querySelector('select')).not.toBeNull());
    const select = sheet.querySelector('select') as HTMLSelectElement;
    // The right already held is not offered again.
    expect([...select.options].map((o) => o.value)).toEqual([
      '',
      'beheerder',
      'lezer',
      'aanvrager',
      'tekenbevoegde',
    ]);
    fireEvent.change(select, { target: { value: 'tekenbevoegde' } });
    await waitFor(() =>
      expect(sheet.querySelector('nldd-inline-dialog')?.getAttribute('text')).toContain(
        'Tekent offertes',
      ),
    );
    fireEvent.submit(sheet.querySelector('form') as HTMLFormElement);
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);

    const dialog = [...document.body.querySelectorAll('nldd-modal-dialog')].find((el) =>
      el.getAttribute('text')?.includes('Tekenbevoegde geven'),
    ) as HTMLElement;
    expect(dialog.getAttribute('supporting-text')).toContain('bindt de organisatie');
    fireEvent.click(button(dialog, 'Ken toe') as Element);
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: 'PUT',
        url: '/api/people/p-1/functions/tekenbevoegde',
      }),
    );
  });

  it('grants an everyday right without the extra question', async () => {
    const { container, calls } = await renderPerson({ person: FULL }, ['beheerder']);
    choose(container, 'Krijgt een recht in grip');
    const sheet = sheetOf('Recht toekennen aan Rik Medewerker');
    await waitFor(() => expect(sheet.querySelector('select')).not.toBeNull());
    fireEvent.change(sheet.querySelector('select') as HTMLSelectElement, {
      target: { value: 'lezer' },
    });
    fireEvent.submit(sheet.querySelector('form') as HTMLFormElement);
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'PUT', url: '/api/people/p-1/functions/lezer' }),
    );
  });

  it('validates on submit, not before', async () => {
    const { container } = await renderPerson({ person: FULL }, ['beheerder']);
    choose(container, 'Wordt ingehuurd');
    const sheet = sheetOf('Inhuur van Rik Medewerker');
    await waitFor(() => expect(sheet.querySelector('form')).not.toBeNull());
    expect(sheet.querySelector('nldd-banner')).toBeNull();
    fireEvent.submit(sheet.querySelector('form') as HTMLFormElement);
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner')?.getAttribute('text')).toContain('leverancier'),
    );
  });

  it('records that someone leaves only after a confirmation', async () => {
    const { container, calls } = await renderPerson({ person: FULL }, ['beheerder']);
    choose(container, 'Vertrekt of wordt inactief');
    const dialog = [...document.body.querySelectorAll('nldd-modal-dialog')].find(
      (el) => el.getAttribute('text') === 'Rik Medewerker inactief maken?',
    ) as HTMLElement;
    expect(calls.some((call) => call.method === 'PATCH')).toBe(false);
    fireEvent.click(button(dialog, 'Maak inactief') as Element);
    await waitFor(() => expect(calls).toContainEqual({ method: 'PATCH', url: '/api/people/p-1' }));
  });

  it('says that roles are missing, and where the proposal to Wies stands', async () => {
    const { container } = await renderPerson(
      {
        person: {
          ...ROSTER,
          ...STAFFING,
          email: null,
          stage: 'prospective',
          starts_on: '2026-09-01',
        },
        roles: [],
        outgoing: [{ person_id: 'p-1', name: 'Rik Medewerker', state: 'open' }],
      },
      ['beheerder'],
    );
    await waitFor(() => expect(identity(container)).toContain('Nog geen rollen'));
    await waitFor(() =>
      expect(identity(container)).toContain('Voorgesteld aan Wies, nog niet overgenomen'),
    );
    // A prospective colleague is not hired through this page.
    expect(menuItems(container)).not.toContain('Wordt ingehuurd');
  });
});

describe('the login of a person', () => {
  const FULL = { ...ROSTER, ...STAFFING };

  it('lets the beheerder unbind a login that is bound, after a confirmation', async () => {
    const { container, calls } = await renderPerson({ person: FULL, loginBound: true }, [
      'beheerder',
    ]);
    await waitFor(() => expect(menuItems(container)).toContain('Ontkoppel de login'));
    choose(container, 'Ontkoppel de login');
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false);
    const dialog = [...document.body.querySelectorAll('nldd-modal-dialog')].find((el) =>
      el.getAttribute('text')?.includes('ontkoppelen'),
    ) as HTMLElement;
    fireEvent.click(button(dialog, 'Ontkoppel login') as Element);
    await waitFor(() =>
      expect(calls).toContainEqual({ method: 'DELETE', url: '/api/people/p-1/login' }),
    );
  });

  it('offers nothing to unbind for someone who never logged in', async () => {
    const { container, calls } = await renderPerson({ person: FULL, loginBound: false }, [
      'beheerder',
    ]);
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/login'))).toBe(true));
    expect(menuItems(container)).not.toContain('Ontkoppel de login');
  });
});
