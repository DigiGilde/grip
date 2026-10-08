import { act, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PATHS } from '@/paths';
import { renderApp } from '@/test/utils';
import { VacancyTextPage } from './VacancyTextPage';

type Editor = HTMLElement & { value?: string };

const VERSION = (id: string, number: number, body: string, by = 'Fictieve Schrijver') => ({
  id,
  number,
  body,
  source: 'human',
  created_at: '2026-10-08T09:00:00Z',
  created_by_name: by,
  by_viewer: false,
});

const WORK = (versions: object[], mayWrite = true) => ({
  vacancy_id: 'v-1',
  texts: [
    {
      kind: 'vacancy_text',
      needed: true,
      state: 'draft',
      state_text: 'In de maak',
      revising: false,
      open_passages: [],
      action: { key: 'offer', text: 'Vraag om een oordeel' },
      may_write: mayWrite,
      may_remark: false,
      may_settle: false,
      versions,
      rounds: [],
      remarks: [],
      latest_changes: [],
    },
  ],
  publications: [],
  may_record_publication: false,
  publication_missing: false,
  drafting_available: false,
});

const START = '## Dit ga je doen\n\nJe bouwt aan [vul aan: het product].';

interface Call {
  method: string;
  path: string;
  body: unknown;
}

function stub(answers: Record<string, { status?: number; body: unknown }[]>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      const path = String(input).split('?')[0] ?? '';
      calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : null });
      const queue = answers[`${method} ${path}`] ?? [];
      const answer = queue.length > 1 ? queue.shift()! : queue[0];
      const status = answer?.status ?? (answer ? 200 : 404);
      return new Response(JSON.stringify(answer?.body ?? { title: 'Niet gevonden', status: 404 }), {
        status,
        headers: {
          'Content-Type': status < 400 ? 'application/json' : 'application/problem+json',
        },
      });
    }),
  );
  return calls;
}

function renderPage() {
  return renderApp(
    <Routes>
      <Route path={PATHS.vacancyTextWrite} element={<VacancyTextPage />} />
      <Route path="/vacatures/:vacancyId/tekst" element={<p data-tab>Tekst tab</p>} />
    </Routes>,
    { path: '/vacatures/v-1/tekst/schrijven' },
  );
}

const editorOf = (container: HTMLElement) => container.querySelector('nldd-text-editor') as Editor;
const type = (container: HTMLElement, value: string) =>
  act(() => {
    editorOf(container).value = value;
    editorOf(container).dispatchEvent(new CustomEvent('input', { detail: { value } }));
  });
const press = (container: HTMLElement, text: string) =>
  act(() => {
    container.querySelector(`nldd-button[text="${text}"]`)?.dispatchEvent(new Event('click'));
  });

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('VacancyTextPage', () => {
  const VACANCY = {
    'GET /api/vacancies/v-1': [{ body: { id: 'v-1', function_title: 'Developer' } }],
  };

  it('opens the latest version in the editor, with what is still open and one primary action', async () => {
    stub({
      ...VACANCY,
      'GET /api/vacancies/v-1/text-work': [{ body: WORK([VERSION('t-1', 1, START)]) }],
    });
    const { container } = renderPage();
    await waitFor(() => expect(editorOf(container)).not.toBeNull());
    expect(container.querySelector('h1')?.textContent).toBe('Vacaturetekst voor Developer');
    expect(
      container.querySelector('nldd-link[text="Terug naar de vacature"]')?.getAttribute('href'),
    ).toBe('/vacatures/v-1/tekst');
    expect(editorOf(container).value).toBe(START);
    // A vacancy text knows a heading, a list and emphasis; nothing about marks is explained.
    expect(
      [...container.querySelectorAll('nldd-toggle-button')].map((el) => el.getAttribute('text')),
    ).toEqual(['Kop', 'Lijst', 'Cursief']);
    expect(container.textContent).not.toContain('##');
    expect(container.textContent).toContain('Nog 1 plek in te vullen');
    expect(
      [...container.querySelectorAll('nldd-button[appearance="primary"]')].map((el) =>
        el.getAttribute('text'),
      ),
    ).toEqual(['Bewaar']);
  });

  it('keeps what is typed in the browser, saves it on the version it started from, and returns', async () => {
    const calls = stub({
      ...VACANCY,
      'GET /api/vacancies/v-1/text-work': [{ body: WORK([VERSION('t-1', 1, START)]) }],
      'POST /api/vacancies/v-1/text-work/versions': [
        { body: WORK([VERSION('t-1', 1, START), VERSION('t-2', 2, 'Nieuw.')]) },
      ],
    });
    const { container } = renderPage();
    await waitFor(() => expect(editorOf(container)).not.toBeNull());
    type(container, '# Dit ga je doen\n\nJe bouwt aan het product.');
    expect(JSON.parse(localStorage.getItem('grip.vacaturetekst.v-1') ?? '{}')).toEqual({
      body: '## Dit ga je doen\n\nJe bouwt aan het product.',
      basedOn: 't-1',
    });
    press(container, 'Bewaar');
    await waitFor(() => expect(container.querySelector('[data-tab]')).not.toBeNull());
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({
      kind: 'vacancy_text',
      body: '## Dit ga je doen\n\nJe bouwt aan het product.',
      based_on_id: 't-1',
    });
    expect(localStorage.getItem('grip.vacaturetekst.v-1')).toBeNull();
  });

  it('puts back a text that was typed and never saved', async () => {
    localStorage.setItem(
      'grip.vacaturetekst.v-1',
      JSON.stringify({ body: 'Half af.', basedOn: 't-1' }),
    );
    stub({
      ...VACANCY,
      'GET /api/vacancies/v-1/text-work': [{ body: WORK([VERSION('t-1', 1, START)]) }],
    });
    const { container } = renderPage();
    await waitFor(() => expect(editorOf(container)?.value).toBe('Half af.'));
    expect(container.textContent).toContain('nog niet had bewaard');
  });

  it('overwrites nothing when a colleague saved in between: shows their text and lets the writer choose', async () => {
    const theirs = WORK([
      VERSION('t-1', 1, START),
      VERSION('t-2', 2, 'Tekst van een collega.', 'Fictieve Collega'),
    ]);
    const calls = stub({
      ...VACANCY,
      'GET /api/vacancies/v-1/text-work': [
        { body: WORK([VERSION('t-1', 1, START)]) },
        { body: theirs },
      ],
      'POST /api/vacancies/v-1/text-work/versions': [
        { status: 409, body: { title: 'Conflict', status: 409, detail: 'Intussen gewijzigd.' } },
        { body: theirs },
      ],
    });
    const { container } = renderPage();
    await waitFor(() => expect(editorOf(container)).not.toBeNull());
    type(container, 'Mijn tekst.');
    press(container, 'Bewaar');
    await waitFor(() =>
      expect(
        container.querySelector('nldd-title[text="Intussen bewaard door een ander"]'),
      ).not.toBeNull(),
    );
    expect(container.textContent).toContain('Tekst van een collega.');
    // Nothing is lost: the writer's text is still in the editor and in this browser.
    expect(editorOf(container).value).toBe('Mijn tekst.');
    expect(JSON.parse(localStorage.getItem('grip.vacaturetekst.v-1') ?? '{}').body).toBe(
      'Mijn tekst.',
    );
    press(container, 'Bewaar mijn tekst');
    await waitFor(() => expect(calls.filter((call) => call.method === 'POST')).toHaveLength(2));
    // The second save builds on the version that came in between.
    expect(calls.filter((call) => call.method === 'POST')[1]?.body).toMatchObject({
      body: 'Mijn tekst.',
      based_on_id: 't-2',
    });
  });

  it('offers no editor to a reader who may not write', async () => {
    stub({
      ...VACANCY,
      'GET /api/vacancies/v-1/text-work': [{ body: WORK([VERSION('t-1', 1, START)], false) }],
    });
    const { container } = renderPage();
    await waitFor(() =>
      expect(
        container.querySelector('nldd-inline-dialog, [text="Deze tekst kun je niet wijzigen"]'),
      ).not.toBeNull(),
    );
    expect(editorOf(container)).toBeNull();
    expect(container.querySelector('nldd-button[appearance="primary"]')).toBeNull();
  });
});
