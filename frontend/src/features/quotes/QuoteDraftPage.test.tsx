import { waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { movedKeys, newSectionKey, sectionState, type DraftSection } from './draftApi';
import { QuoteDraftPage } from './QuoteDraftPage';
import { clickButton, mockApi, texts } from './testing';

const section = (overrides: Partial<DraftSection>): DraftSection => ({
  key: 'inleiding',
  heading: 'Inleiding',
  body: '',
  hint: 'Waarom deze opdracht, in een paar zinnen.',
  included: true,
  with_costs: false,
  draftable: true,
  origin: 'empty',
  settled: true,
  version: 3,
  optional: true,
  removable: true,
  movable: true,
  ...overrides,
});

const DRAFT = {
  saved: true,
  may_edit: true,
  drafting_available: true,
  problems: [{ key: 'inleiding', problem: 'Nog geen tekst.' }],
  subject: 'Offerte Opdracht Alfa',
  addressee: ['Voorbeeldministerie', 'Postbus 1'],
  salutation: 'Geachte heer, mevrouw,',
  opening: '',
  closing: '',
  client_signatory: { name: '', function: '' },
  head_version: 2,
  outline_version: 5,
  sections: [
    section({}),
    section({
      key: 'kosten',
      heading: 'Kosten',
      with_costs: true,
      draftable: false,
      optional: false,
      removable: false,
    }),
    section({
      key: 'voorwaarden',
      heading: 'Leveringsvoorwaarden',
      body: 'Op deze offerte zijn de **voorwaarden** van toepassing.\n\n- Betaling per maand\n- Opzegging per kwartaal',
      origin: 'standard',
      draftable: false,
      optional: false,
      removable: false,
    }),
  ],
};

const PREVIEW = {
  assignment_id: 'a-1',
  assignment_name: 'Opdracht Alfa',
  assignment_status: 'draft',
  can_issue: true,
  may_issue: true,
  problem: null,
  content: {
    name: 'Opdracht Alfa',
    context_refs: [],
    lines: [],
    subtotals_per_year: [],
    total_cents: 17280000,
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

function renderPage(
  replies: Record<string, unknown> = {},
  path = '/opdrachten/a-1/offerte/schrijven',
) {
  const api = mockApi({
    '/api/assignments/a-1/quote-draft': DRAFT,
    '/api/assignments/a-1/quote-preview': PREVIEW,
    ...replies,
  });
  const view = renderApp(
    <Routes>
      <Route path="/opdrachten/:assignmentId/offerte/schrijven" element={<QuoteDraftPage />} />
      <Route path="/opdrachten/:assignmentId/offerte" element={<p>de offertetab</p>} />
    </Routes>,
    { path },
  );
  return { ...api, container: view.container };
}

const loaded = (container: HTMLElement) =>
  waitFor(() => expect(container.querySelector('[data-section]')).not.toBeNull());
const field = (container: HTMLElement) =>
  container.querySelector('nldd-multi-line-text-field') as HTMLElement;
const type = (container: HTMLElement, value: string) =>
  field(container).dispatchEvent(new CustomEvent('input', { detail: { value } }));
/** The state of each section, as its row says it. */
const states = (container: HTMLElement, selector: string) =>
  [...container.querySelectorAll(`${selector} > * nldd-list-item nldd-text-cell`)]
    .map((el) => el.getAttribute('supporting-text'))
    .filter((text): text is string => text !== null);
const openSheet = () =>
  [...document.body.querySelectorAll('nldd-sheet')].find((el) => el.hasAttribute('open'));

describe('QuoteDraftPage', () => {
  it('shows the letter as sections in order, each with its state, all closed', async () => {
    const { container } = renderPage();
    await loaded(container);
    expect(container.querySelector('h1')?.textContent).toBe('Offerte voor Opdracht Alfa');
    expect(texts(container, '[data-section] nldd-list-item nldd-text-cell')).toEqual([
      'Inleiding',
      'Kosten',
      'Leveringsvoorwaarden',
    ]);
    expect(states(container, '[data-section]')).toEqual([
      'Leeg',
      'Bedragen uit de begroting',
      'Standaardtekst',
    ]);
    expect(container.querySelector('nldd-multi-line-text-field')).toBeNull();
    // One primary action, not available yet, with the reason next to it as a way in.
    expect(texts(container, 'nldd-button[appearance="primary"]')).toEqual(['Maak offerte']);
    expect(
      container.querySelector('nldd-button[appearance="primary"]')?.hasAttribute('disabled'),
    ).toBe(true);
    // The reason stands above the button, and names where to begin; the row
    // of that section is the one that offers to write.
    expect(container.textContent).toContain('Nog één onderdeel te schrijven: Inleiding.');
    expect(container.querySelector('[data-problems]')).toBeNull();
    const rowButtons = [...container.querySelectorAll('[data-section] nldd-button')];
    expect(rowButtons.map((el) => el.getAttribute('appearance'))).toEqual([
      'secondary',
      'neutral-transparent',
      'neutral-transparent',
    ]);
    expect(
      [...container.querySelectorAll('nldd-link')]
        .find((el) => el.getAttribute('text') === 'Bekijk voorbeeld (pdf)')
        ?.getAttribute('href'),
    ).toBe('/api/assignments/a-1/quote-draft/preview');
  });

  it('shows a standard text as it will print, not as a field', async () => {
    const { container } = renderPage({}, '/opdrachten/a-1/offerte/schrijven?onderdeel=voorwaarden');
    await loaded(container);
    const block = container.querySelector('[data-section="voorwaarden"]') as Element;
    expect(block.querySelector('nldd-multi-line-text-field')).toBeNull();
    expect(block.querySelector('strong')?.textContent).toBe('voorwaarden');
    expect([...block.querySelectorAll('li')].map((el) => el.textContent)).toEqual([
      'Betaling per maand',
      'Opzegging per kwartaal',
    ]);
    expect(block.textContent).toContain('standaardtekst van de organisatie');
    // Not a beheerder: no way to Beheer.
    expect(texts(block, 'nldd-link')).toEqual([]);
  });

  it('shows the amounts read-only with the way to the budget', async () => {
    const { container } = renderPage({}, '/opdrachten/a-1/offerte/schrijven?onderdeel=kosten');
    await loaded(container);
    const block = container.querySelector('[data-section="kosten"]') as Element;
    expect(block.querySelector('nldd-table')).not.toBeNull();
    expect(block.querySelector('nldd-link')?.getAttribute('href')).toBe(
      '/opdrachten/a-1/begroting',
    );
    expect(block.querySelector('nldd-multi-line-text-field')).toBeNull();
  });

  it('keeps what is typed in the browser until the server confirmed the save', async () => {
    const saved = {
      ...DRAFT,
      problems: [],
      sections: [
        section({ body: 'De opdracht in het kort.', origin: 'written' }),
        ...DRAFT.sections.slice(1),
      ],
    };
    const { container, calls } = renderPage(
      { 'PUT /api/assignments/a-1/quote-draft/sections/inleiding': saved },
      '/opdrachten/a-1/offerte/schrijven?onderdeel=inleiding',
    );
    await loaded(container);
    await waitFor(() => expect(field(container)).not.toBeNull());
    expect(container.textContent).toContain('Waarom deze opdracht, in een paar zinnen.');
    type(container, 'De opdracht in het kort.');
    await waitFor(() =>
      expect(field(container).getAttribute('value')).toBe('De opdracht in het kort.'),
    );
    expect(JSON.parse(localStorage.getItem('grip.offertetekst.a-1.inleiding') ?? '{}').text).toBe(
      'De opdracht in het kort.',
    );
    expect(container.textContent).toContain('Nog niet bewaard');
    clickButton(container, 'Bewaar');
    await waitFor(() => expect(calls.some((call) => call.method === 'PUT')).toBe(true));
    expect(calls.find((call) => call.method === 'PUT')?.body).toEqual({
      body: 'De opdracht in het kort.',
      version: 3,
    });
    // Confirmed: the copy is gone, the state follows, the quote can be made.
    await waitFor(() => expect(localStorage.getItem('grip.offertetekst.a-1.inleiding')).toBeNull());
    await waitFor(() =>
      expect(states(container, '[data-section="inleiding"]')).toEqual(['Zelf geschreven']),
    );
    expect(container.querySelector('[data-problems]')).toBeNull();
    expect(
      container.querySelector('nldd-button[appearance="primary"]')?.hasAttribute('disabled'),
    ).toBe(false);
  });

  it('puts back a text that was typed and never saved', async () => {
    localStorage.setItem(
      'grip.offertetekst.a-1.inleiding',
      JSON.stringify({ text: 'Half af', base: '', at: '2026-10-08T09:00:00Z' }),
    );
    const { container } = renderPage({}, '/opdrachten/a-1/offerte/schrijven?onderdeel=inleiding');
    await loaded(container);
    await waitFor(() => expect(field(container)?.getAttribute('value')).toBe('Half af'));
    expect(container.textContent).toContain('was nog niet bewaard en staat hier weer');
  });

  it('does not overwrite what a colleague saved in the meantime, and loses nothing', async () => {
    const theirs = {
      ...DRAFT,
      sections: [
        section({ body: 'Tekst van een collega', origin: 'written', version: 4 }),
        ...DRAFT.sections.slice(1),
      ],
    };
    const { container } = renderPage(
      {
        'PUT /api/assignments/a-1/quote-draft/sections/inleiding': {
          status: 409,
          body: {
            title: 'Conflict',
            status: 409,
            detail: 'Dit onderdeel is intussen gewijzigd.',
            changed_by: 'Collega Voorbeeld',
            changed_at: '2026-10-08T10:15:00Z',
            current: theirs,
          },
        },
      },
      '/opdrachten/a-1/offerte/schrijven?onderdeel=inleiding',
    );
    await loaded(container);
    await waitFor(() => expect(field(container)).not.toBeNull());
    type(container, 'Mijn tekst');
    await waitFor(() => expect(field(container).getAttribute('value')).toBe('Mijn tekst'));
    clickButton(container, 'Bewaar');
    await waitFor(() =>
      expect(container.querySelector('nldd-banner[variant="warning"]')?.getAttribute('text')).toBe(
        'Collega Voorbeeld heeft dit onderdeel intussen gewijzigd',
      ),
    );
    // Their text is shown; mine is still in the field and in this browser.
    expect(container.querySelector('[data-their-text]')?.textContent).toBe('Tekst van een collega');
    expect(field(container).getAttribute('value')).toBe('Mijn tekst');
    expect(JSON.parse(localStorage.getItem('grip.offertetekst.a-1.inleiding') ?? '{}').text).toBe(
      'Mijn tekst',
    );

    // Keeping mine is a new save on top of theirs.
    const kept = {
      ...theirs,
      sections: [
        section({ body: 'Mijn tekst', origin: 'written', version: 5 }),
        ...DRAFT.sections.slice(1),
      ],
    };
    const second = mockApi({ 'PUT /api/assignments/a-1/quote-draft/sections/inleiding': kept });
    clickButton(container, 'Bewaar mijn tekst');
    await waitFor(() => expect(second.calls.some((call) => call.method === 'PUT')).toBe(true));
    expect(second.calls.find((call) => call.method === 'PUT')?.body).toEqual({
      body: 'Mijn tekst',
      version: 4,
    });
    await waitFor(() =>
      expect(container.querySelector('nldd-banner[variant="warning"]')).toBeNull(),
    );
    expect(localStorage.getItem('grip.offertetekst.a-1.inleiding')).toBeNull();
  });

  it("takes the colleague's text when the person chooses that", async () => {
    const theirs = {
      ...DRAFT,
      problems: [],
      sections: [
        section({ body: 'Tekst van een collega', origin: 'written', version: 4 }),
        ...DRAFT.sections.slice(1),
      ],
    };
    const { container } = renderPage(
      {
        'PUT /api/assignments/a-1/quote-draft/sections/inleiding': {
          status: 409,
          body: { status: 409, changed_by: null, changed_at: null, current: theirs },
        },
      },
      '/opdrachten/a-1/offerte/schrijven?onderdeel=inleiding',
    );
    await loaded(container);
    await waitFor(() => expect(field(container)).not.toBeNull());
    type(container, 'Mijn tekst');
    await waitFor(() => expect(field(container).getAttribute('value')).toBe('Mijn tekst'));
    clickButton(container, 'Bewaar');
    await waitFor(() => expect(container.querySelector('[data-their-text]')).not.toBeNull());
    expect(container.querySelector('nldd-banner[variant="warning"]')?.getAttribute('text')).toBe(
      'Een collega heeft dit onderdeel intussen gewijzigd',
    );
    clickButton(container, 'Neem de andere tekst over');
    await waitFor(() =>
      expect(field(container).getAttribute('value')).toBe('Tekst van een collega'),
    );
    expect(states(container, '[data-section="inleiding"]')).toEqual(['Zelf geschreven']);
  });

  it('keeps what was filled in when the head of the letter changed under it', async () => {
    const { container, calls } = renderPage({
      'PATCH /api/assignments/a-1/quote-draft': {
        status: 409,
        body: {
          status: 409,
          changed_by: 'Collega Voorbeeld',
          changed_at: '2026-10-08T10:15:00Z',
          current: { ...DRAFT, subject: 'Offerte van de collega', head_version: 3 },
        },
      },
    });
    await loaded(container);
    clickButton(container, 'Wijzig');
    await waitFor(() => expect(openSheet()).toBeDefined());
    const sheet = openSheet() as Element;
    sheet
      .querySelector('nldd-text-field')
      ?.dispatchEvent(new CustomEvent('input', { detail: { value: 'Mijn betreft' } }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-text-field')?.getAttribute('value')).toBe('Mijn betreft'),
    );
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(
        sheet.querySelector('nldd-banner[variant="critical"]')?.getAttribute('text'),
      ).toContain('Collega Voorbeeld heeft dit intussen gewijzigd'),
    );
    expect(calls.find((call) => call.method === 'PATCH')?.body).toMatchObject({ head_version: 2 });
    // Still open, with what was typed; the page behind it shows the latest.
    expect(sheet.hasAttribute('open')).toBe(true);
    expect(sheet.querySelector('nldd-text-field')?.getAttribute('value')).toBe('Mijn betreft');
    expect(texts(container, 'nldd-list nldd-text-cell')).toContain('Offerte van de collega');
  });

  it('shows a model draft as a proposal until someone saves it', async () => {
    const proposed = {
      ...DRAFT,
      problems: [
        { key: 'inleiding', problem: 'Een concept van het taalmodel dat nog niet is vastgesteld.' },
      ],
      sections: [
        section({ body: 'Een voorstel voor de inleiding.', origin: 'generated', settled: false }),
        ...DRAFT.sections.slice(1),
      ],
    };
    const { container, calls } = renderPage(
      { 'POST /api/assignments/a-1/quote-draft/sections/inleiding/draft': proposed },
      '/opdrachten/a-1/offerte/schrijven?onderdeel=inleiding',
    );
    await loaded(container);
    await waitFor(() => expect(field(container)).not.toBeNull());
    clickButton(container, 'Stel een concept op');
    await waitFor(() => expect(container.querySelector('[data-proposal]')).not.toBeNull());
    expect(calls.some((call) => call.url.endsWith('/sections/inleiding/draft'))).toBe(true);
    expect(field(container).getAttribute('value')).toBe('Een voorstel voor de inleiding.');
    expect(states(container, '[data-section="inleiding"]')).toEqual([
      'Concept van het taalmodel: nog niet vastgesteld',
    ]);
    expect(texts(container, '[data-section="inleiding"] nldd-button')).toContain('Stel vast');
    // Still in the way of the quote.
    expect(
      container.querySelector('nldd-button[appearance="primary"]')?.hasAttribute('disabled'),
    ).toBe(true);
  });

  it('shows nothing about the language model where it is not available', async () => {
    const { container } = renderPage(
      { '/api/assignments/a-1/quote-draft': { ...DRAFT, drafting_available: false } },
      '/opdrachten/a-1/offerte/schrijven?onderdeel=inleiding',
    );
    await loaded(container);
    await waitFor(() => expect(field(container)).not.toBeNull());
    expect(texts(container, 'nldd-button').join(' ')).not.toMatch(/concept|Herschrijf/);
    expect(container.textContent).not.toMatch(/taalmodel/i);
  });

  it('reorders and adds sections through the outline', async () => {
    const { container, calls } = renderPage({
      'PUT /api/assignments/a-1/quote-draft/outline': DRAFT,
    });
    await loaded(container);
    expect(texts(container, '[data-section="inleiding"] nldd-menu-item')).toEqual([
      'Zet later in de brief',
      'Laat weg uit deze offerte',
      'Verwijder dit onderdeel',
    ]);
    // What a section allows comes from the server, not from a guess here.
    expect(texts(container, '[data-section="voorwaarden"] nldd-menu-item')).toEqual([
      'Zet eerder in de brief',
    ]);
    container
      .querySelector('[data-section="inleiding"] nldd-menu-item')
      ?.dispatchEvent(new CustomEvent('select', { bubbles: true }));
    await waitFor(() => expect(calls.some((call) => call.method === 'PUT')).toBe(true));
    expect(calls.find((call) => call.method === 'PUT')?.body).toEqual({
      keys: ['kosten', 'inleiding', 'voorwaarden'],
      new_sections: [],
      outline_version: 5,
    });
    clickButton(container, 'Voeg een onderdeel toe');
    await waitFor(() => expect(openSheet()).toBeDefined());
    openSheet()
      ?.querySelector('nldd-text-field')
      ?.dispatchEvent(new CustomEvent('input', { detail: { value: 'Werkwijze en planning' } }));
    await waitFor(() =>
      expect(openSheet()?.querySelector('nldd-text-field')?.getAttribute('value')).toBe(
        'Werkwijze en planning',
      ),
    );
    openSheet()
      ?.querySelector('nldd-form')
      ?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(calls.filter((call) => call.method === 'PUT')).toHaveLength(2));
    expect(calls.filter((call) => call.method === 'PUT')[1]?.body).toEqual({
      keys: ['inleiding', 'kosten', 'voorwaarden', 'werkwijze-en-planning'],
      new_sections: [{ key: 'werkwijze-en-planning', heading: 'Werkwijze en planning' }],
      outline_version: 5,
    });
  });

  it('gives a reader the letter without anything to change', async () => {
    const { container } = renderPage({
      '/api/assignments/a-1/quote-draft': { ...DRAFT, may_edit: false },
    });
    await loaded(container);
    expect(texts(container, 'nldd-button').filter((text) => text !== 'Bekijk')).toEqual([]);
    expect(container.querySelector('nldd-icon-button')).toBeNull();
    expect(texts(container, 'nldd-link')).toContain('Bekijk voorbeeld (pdf)');
  });

  it('makes the quote and goes back to the quote tab', async () => {
    const { container, calls } = renderPage({
      '/api/assignments/a-1/quote-draft': { ...DRAFT, problems: [] },
      'POST /api/assignments/a-1/quotes': { id: 'q-9', status: 'issued' },
    });
    await loaded(container);
    clickButton(container, 'Maak offerte');
    await waitFor(() => expect(openSheet()).toBeDefined());
    openSheet()
      ?.querySelector('nldd-form')
      ?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() => expect(container.textContent).toContain('de offertetab'));
    expect(calls.find((call) => call.method === 'POST')?.url).toBe('/api/assignments/a-1/quotes');
  });
});

describe('what a section allows', () => {
  it('shows no menu for a section that can neither move nor go', async () => {
    const { container } = renderPage({
      '/api/assignments/a-1/quote-draft': {
        ...DRAFT,
        sections: [
          section({ movable: false, optional: false, removable: false }),
          ...DRAFT.sections.slice(1),
        ],
      },
    });
    await loaded(container);
    expect(container.querySelector('[data-section="inleiding"] nldd-icon-button')).toBeNull();
    expect(container.querySelector('[data-section="kosten"] nldd-icon-button')).not.toBeNull();
  });
});

describe('helpers of the draft', () => {
  it('names where a text comes from', () => {
    expect(sectionState(section({ included: false }))).toBe('Niet in deze offerte');
    expect(sectionState(section({ origin: 'generated', body: 'x', settled: true }))).toBe(
      'Opgesteld met het taalmodel, vastgesteld',
    );
  });

  it('moves a section and stays put at an edge', () => {
    expect(movedKeys(['a', 'b', 'c'], 'c', -1)).toEqual(['a', 'c', 'b']);
    expect(movedKeys(['a', 'b', 'c'], 'a', -1)).toEqual(['a', 'b', 'c']);
  });

  it('makes a key from a heading that no other section has', () => {
    expect(newSectionKey('Werkwijze & planning', [])).toBe('werkwijze-planning');
    expect(newSectionKey('Inleiding', ['inleiding'])).toBe('inleiding-2');
    expect(newSectionKey('???', [])).toBe('onderdeel');
  });
});
