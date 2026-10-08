import { fireEvent, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp, TEST_PERSON } from '@/test/utils';
import { PersonPage } from './PersonPage';
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
}

function mock({ person, kpi, loginBound }: Mock) {
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
      else if (path === '/api/people/p-1/login')
        body = { bound: method === 'DELETE' ? false : Boolean(loginBound) };
      else if (path.startsWith('/api/people/p-1/functions/')) body = person;
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
  await waitFor(() => expect(view.container.querySelector('nldd-list')).not.toBeNull());
  return { container: view.container, calls };
}

const sections = (container: HTMLElement) =>
  texts(container, 'nldd-container > nldd-title[heading-level="2"]');
const buttons = (root: ParentNode) => texts(root, 'nldd-button');
const button = (root: ParentNode, text: string) =>
  [...root.querySelectorAll('nldd-button')].find((el) => el.getAttribute('text') === text);

describe('what a reader sees of a person', () => {
  it('shows only who and how to someone with roster data', async () => {
    const { container } = await renderPerson({ person: ROSTER });
    expect(sections(container)).toEqual(['Wie en hoe']);
    expect(container.querySelector('h1')?.textContent).toBe('Rik Medewerker');
    // No section, field or action for anything else is in the document.
    const html = document.body.innerHTML;
    for (const word of [
      'Inzetschaal',
      'Kostprijs',
      'Declarabiliteit',
      'Rechten in grip',
      'Inloggen',
    ]) {
      expect(html).not.toContain(word);
    }
    expect(buttons(document.body)).toEqual([]);
  });

  it('adds inzet and rights for someone who sees staffing, without amounts', async () => {
    const { container } = await renderPerson({ person: { ...ROSTER, ...STAFFING } });
    expect(sections(container)).toEqual(['Wie en hoe', 'Inzet', 'Rechten in grip']);
    const facts = texts(container, 'nldd-list nldd-text-cell');
    expect(facts).toContain('In dienst');
    expect(facts.some((text) => text.includes('2 opdrachten') && text.includes('80%'))).toBe(true);
    expect(container.querySelector('nldd-link[href="/inzet?persoon=p-1"]')).not.toBeNull();
    expect(document.body.innerHTML).not.toContain('€');
    expect(buttons(document.body)).toEqual([]);
  });

  it('adds scale and KPI for a line manager, still without cost', async () => {
    const { container } = await renderPerson({
      person: { ...ROSTER, ...STAFFING, ...RATE },
      kpi: KPI,
    });
    await waitFor(() => expect(sections(container)).toContain('Declarabiliteit 2026'));
    expect(sections(container)).toEqual([
      'Wie en hoe',
      'Inzet',
      'Inzetschaal',
      'Declarabiliteit 2026',
      'Rechten in grip',
    ]);
    const facts = texts(container, 'nldd-list nldd-text-cell');
    expect(facts).toContain('Schaal 14, categorie D');
    expect(document.body.innerHTML).not.toContain('Kostprijs');
    expect(document.body.innerHTML).not.toContain('Marge');
  });

  it('shows a hired person as one fact, with cost only when it is there', async () => {
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
    let facts = texts(container, 'nldd-list nldd-text-cell');
    expect(facts).toContain('Ingehuurd via Voorbeeld Detachering');
    expect(document.body.innerHTML).not.toContain('Kostprijs');

    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    const withCost = await renderPerson({
      person: { ...hired, cost_monthly_rate_cents: 1500000, margin_monthly_cents: 300000 },
    });
    facts = texts(withCost.container, 'nldd-list nldd-text-cell');
    expect(facts.some((text) => text.includes('15.000'))).toBe(true);
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
    const facts = texts(container, 'nldd-list nldd-text-cell');
    expect(facts).toContain('Aanstaande collega, start op 1 sep 2026');
    expect(facts).toContain('Nog geen e-mailadres');
    const engaged = container.querySelector('nldd-text-cell[overline="Verbonden als"]');
    expect(engaged?.getAttribute('supporting-text')).toContain('Inloggen kan pas');
  });

  it('answers not found for a person the reader may not see', async () => {
    mock({ person: null as unknown as object });
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

describe('what the beheerder can do', () => {
  const FULL = { ...ROSTER, ...STAFFING, ...RATE };

  it('opens nothing by default: each section has one action and no open form', async () => {
    const { container } = await renderPerson({ person: FULL, kpi: KPI }, ['beheerder']);
    await waitFor(() => expect(sections(container)).toContain('Declarabiliteit 2026'));
    expect(container.querySelector('form')).toBeNull();
    expect(document.body.querySelectorAll('form')).toHaveLength(0);
    expect(buttons(container)).toEqual([
      'Wijzig gegevens',
      'Leg inhuur vast',
      'Nieuwe inzetschaal',
      'Stel target in',
      'Ken een recht toe',
      'Trek in',
    ]);
  });

  it('shows since when and by whom a right was granted', async () => {
    const { container } = await renderPerson({ person: FULL }, ['beheerder']);
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('Planner');
    expect(cells).toContain('Sinds 1 mrt 2026, toegekend door Bea Beheerder');
    expect(document.body.innerHTML).not.toContain('gaat direct in');
  });

  it('revokes a right only after a confirmation', async () => {
    const { container, calls } = await renderPerson({ person: FULL }, ['beheerder']);
    fireEvent.click(button(container, 'Trek in') as Element);
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

  it('explains why the only beheerder cannot lose that right', async () => {
    const sole = {
      ...FULL,
      functions: ['beheerder'],
      function_grants: [{ function: 'beheerder', since: '2026-01-05', granted_by_name: null }],
      is_sole_beheerder: true,
    };
    const { container } = await renderPerson({ person: sole }, ['beheerder']);
    expect(button(container, 'Trek in')).toBeUndefined();
    const cells = [...container.querySelectorAll('nldd-table nldd-text-cell')];
    expect(cells.some((cell) => cell.getAttribute('text')?.includes('bij de inrichting'))).toBe(
      true,
    );
    expect(
      cells.some((cell) => cell.getAttribute('supporting-text')?.includes('enige beheerder')),
    ).toBe(true);
  });

  it('asks for confirmation before granting a right that reaches far', async () => {
    const { container, calls } = await renderPerson({ person: FULL }, ['beheerder']);
    fireEvent.click(button(container, 'Ken een recht toe') as Element);
    const sheet = document.body
      .querySelector('nldd-top-title-bar[text="Recht toekennen aan Rik Medewerker"]')
      ?.closest('nldd-sheet') as HTMLElement;
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
    fireEvent.click(button(container, 'Ken een recht toe') as Element);
    const sheet = document.body
      .querySelector('nldd-top-title-bar[text="Recht toekennen aan Rik Medewerker"]')
      ?.closest('nldd-sheet') as HTMLElement;
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
    fireEvent.click(button(container, 'Leg inhuur vast') as Element);
    const sheet = document.body
      .querySelector('nldd-top-title-bar[text="Inhuur van Rik Medewerker"]')
      ?.closest('nldd-sheet') as HTMLElement;
    await waitFor(() => expect(sheet.querySelector('form')).not.toBeNull());
    expect(sheet.querySelector('nldd-banner')).toBeNull();
    fireEvent.submit(sheet.querySelector('form') as HTMLFormElement);
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner')?.getAttribute('text')).toContain('leverancier'),
    );
  });
});

describe('the login of a person', () => {
  const FULL = { ...ROSTER, ...STAFFING };

  it('lets the beheerder unbind a login that is bound, after a confirmation', async () => {
    const { container, calls } = await renderPerson({ person: FULL, loginBound: true }, [
      'beheerder',
    ]);
    await waitFor(() => expect(button(container, 'Ontkoppel login')).toBeDefined());
    const unbind = button(container, 'Ontkoppel login') as Element;
    expect(unbind).toHaveAttribute('accessible-label', 'Ontkoppel de login van Rik Medewerker');
    fireEvent.click(unbind);
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
    const { container } = await renderPerson({ person: FULL, loginBound: false }, ['beheerder']);
    await waitFor(() =>
      expect(container.querySelector('nldd-title[text="Inloggen"]')).toHaveAttribute(
        'supporting-text',
        'Nog niet ingelogd; de eerste keer inloggen koppelt het account',
      ),
    );
    expect(button(container, 'Ontkoppel login')).toBeUndefined();
  });

  it('does not ask about the login for someone who does not manage persons', async () => {
    const { container, calls } = await renderPerson({ person: FULL, loginBound: true });
    expect(calls.filter((call) => call.url.endsWith('/login'))).toEqual([]);
    expect(container.querySelector('nldd-title[text="Inloggen"]')).toBeNull();
  });
});
