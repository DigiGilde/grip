import { fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '@/AppRoutes';
import { mockApi, texts } from '@/features/team/ui/testing';
import { APP_ROUTES } from '@/routes';
import { renderApp } from '@/test/utils';
import type { PriceImpact } from './api';
import { activationSentences, impactSentences } from './impact';
import { RatesPage } from './RatesPage';
import { firstDayOfNextYear, momentOf, validityText } from './validity';

const BANDS = {
  rate_bands: [
    { category: 'A', monthly_rate_cents: 900000 },
    { category: 'D', monthly_rate_cents: 1800000 },
  ],
  scale_bands: [
    { scale: 14, category: 'D' },
    { scale: 15, category: 'D' },
  ],
};
// A card that holds whatever day the test runs on, one before it, and a draft
// that starts in the middle of a year.
const CURRENT = {
  id: 'c-now',
  name: 'Tarieven lopend',
  valid_from: '2020-07-01',
  valid_to: null,
  status: 'active',
  ...BANDS,
};
const EARLIER = {
  id: 'c-old',
  name: 'Tarieven eerder',
  valid_from: '2019-01-01',
  valid_to: '2020-06-30',
  status: 'closed',
  ...BANDS,
};
const DRAFT = {
  id: 'c-draft',
  name: 'Tarieven vanaf 15 juli 2099',
  valid_from: '2099-07-15',
  valid_to: null,
  status: 'draft',
  ...BANDS,
};

const NO_IMPACT: PriceImpact = {
  budget_lines_changed: 0,
  budget_difference_cents: 0,
  allocations_changed: 0,
  open_difference_cents: 0,
  closed_difference_cents: 0,
  correction_cents: 0,
  unpriced_months: 0,
  reaches_into_the_past: false,
  assignments: [],
};

/** Amounts are written with a non-breaking space after the euro sign. */
const plain = (text: string | null) => (text ?? '').replace(/\u00a0/g, ' ');

afterEach(() => vi.unstubAllGlobals());

async function renderRates(
  cards: object[],
  mayManage: boolean,
  extra: Record<string, unknown> = {},
) {
  const api = mockApi({
    '/api/rates/cards': { items: cards, may_manage: mayManage, default_increase_pct: '5.00' },
    '/api/rates/valid': { stretches: [], has_gap: false },
    ...extra,
  });
  const view = renderApp(<RatesPage />, { path: '/beheer/tarieven' });
  await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
  return { container: view.container, calls: api.calls };
}

const buttons = (root: ParentNode) => texts(root, 'nldd-button');
const openSheet = (title: string) =>
  [...document.body.querySelectorAll('nldd-sheet')].find(
    (sheet) =>
      sheet.hasAttribute('open') &&
      sheet.querySelector('nldd-top-title-bar')?.getAttribute('text') === title,
  ) as HTMLElement | undefined;

describe('the time line of rate cards', () => {
  it('shows which card holds now, what came before and what is coming', async () => {
    const { container } = await renderRates([DRAFT, CURRENT, EARLIER], false);
    const timeline = container.querySelector('nldd-table') as HTMLElement;
    expect(texts(timeline, 'nldd-link')).toEqual([
      'Tarieven vanaf 15 juli 2099',
      'Tarieven lopend',
      'Tarieven eerder',
    ]);
    expect(texts(timeline, 'nldd-badge')).toEqual(['Concept', 'Geldt nu', 'Voorbij, gesloten']);
    const cells = texts(timeline, 'nldd-text-cell');
    expect(cells).toContain('geldig vanaf 1 jul 2020');
    expect(cells).toContain('geldig van 1 jan 2019 t/m 30 jun 2020');
  });

  it('opens the card that holds now, and another one on a click', async () => {
    const { container } = await renderRates([DRAFT, CURRENT, EARLIER], false);
    const heading = () =>
      [...container.querySelectorAll('nldd-title[heading-level="2"]')].map((el) =>
        el.getAttribute('text'),
      );
    expect(heading()).toEqual(['Tarieven lopend']);
    const link = [...container.querySelectorAll('nldd-table nldd-link')].find(
      (el) => el.getAttribute('text') === 'Tarieven eerder',
    );
    fireEvent.click(link as Element);
    await waitFor(() => expect(heading()).toEqual(['Tarieven eerder']));
  });

  it('never names a card by a year, and has no year select', async () => {
    const { container } = await renderRates([DRAFT, CURRENT, EARLIER], true);
    expect(container.querySelector('select')).toBeNull();
    const html = container.innerHTML;
    for (const phrase of ['Nieuw jaar', 'Sluit dit jaar', 'Tarievenkaart 20', '>Jaar<']) {
      expect(html).not.toContain(phrase);
    }
  });

  it('shows a stretch no card prices as a gap', async () => {
    const { container } = await renderRates([CURRENT, EARLIER], false, {
      '/api/rates/valid': {
        has_gap: true,
        stretches: [
          { start_date: '2020-03-01', end_date: '2020-03-31', card_id: null, card_name: null },
        ],
      },
    });
    await waitFor(() => expect(texts(container, 'nldd-badge')).toContain('Gat: niet te prijzen'));
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain(
      'van 1 mrt 2020 t/m 31 mrt 2020',
    );
  });

  it('offers a reader nothing that changes', async () => {
    const { container } = await renderRates([CURRENT], false);
    expect(buttons(container)).toEqual([]);
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain('14, 15');
    expect(texts(container, 'nldd-table nldd-text-cell')).toContain('Niet ingevuld');
    expect(document.body.querySelectorAll('form')).toHaveLength(0);
  });

  it('gives the manager one primary action and nothing open by default', async () => {
    const { container } = await renderRates([CURRENT], true);
    const primary = [...container.querySelectorAll('nldd-button[appearance="primary"]')];
    expect(primary.map((el) => el.getAttribute('text'))).toEqual(['Nieuwe tarievenkaart']);
    expect(openSheet('Nieuwe tarievenkaart')).toBeUndefined();
  });

  it('says so when there is no card yet', async () => {
    mockApi({ '/api/rates/cards': { items: [], may_manage: false, default_increase_pct: '5.00' } });
    const { container } = renderApp(<RatesPage />, { path: '/beheer/tarieven' });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain('Er is nog geen tarievenkaart'),
    );
  });

  it('shows an error when the request fails', async () => {
    mockApi({});
    const { container } = renderApp(<RatesPage />, { path: '/beheer/tarieven' });
    await waitFor(() => expect(container.querySelector('nldd-banner')).not.toBeNull());
  });
});

describe('a new rate card', () => {
  const PREVIEW = {
    copy_from_id: 'c-now',
    copy_from_name: 'Tarieven lopend',
    increase_pct: '5',
    rounding: 'euro',
    rates: [
      {
        category: 'D',
        old_monthly_rate_cents: 1800000,
        new_monthly_rate_cents: 1890000,
        difference_cents: 90000,
      },
    ],
  };

  it('starts from any date, with the first of next year only as the default', async () => {
    const { container, calls } = await renderRates([CURRENT], true, {
      '/api/rates/indexation-preview': PREVIEW,
    });
    fireEvent.click(
      [...container.querySelectorAll('nldd-button')].find(
        (el) => el.getAttribute('text') === 'Nieuwe tarievenkaart',
      ) as Element,
    );
    await waitFor(() => expect(openSheet('Nieuwe tarievenkaart')).toBeDefined());
    const sheet = openSheet('Nieuwe tarievenkaart') as HTMLElement;
    const date = sheet.querySelector('nldd-date-field');
    expect(date?.getAttribute('value') ?? (date as unknown as { value: string }).value).toMatch(
      /^\d{4}-01-01$/,
    );
    expect(
      sheet.querySelector('nldd-form-field[supporting-label*="midden in een jaar"]'),
    ).not.toBeNull();
    expect(sheet.querySelector('nldd-banner')).toBeNull();

    await waitFor(() => expect(sheet.querySelector('nldd-table')).not.toBeNull());
    const preview = new URL(
      calls.find((url) => url.includes('indexation-preview')) ?? '',
      'http://test',
    );
    expect(preview.searchParams.get('valid_from')).toMatch(/^\d{4}-01-01$/);
    expect(preview.searchParams.get('increase_pct')).toBe('5');
    expect(preview.searchParams.get('rounding')).toBe('euro');
    const cells = texts(sheet, 'nldd-table nldd-text-cell');
    expect(cells.some((text) => text.includes('18.900'))).toBe(true);
    expect(
      sheet.querySelector('nldd-title[supporting-text="Op basis van Tarieven lopend"]'),
    ).not.toBeNull();
    const options = [...sheet.querySelectorAll('option')].map((o) => o.textContent);
    expect(options).toEqual(["Hele euro's", 'Tientallen', 'Vijftigtallen']);
  });
});

describe('activating a draft', () => {
  it('says in plain sentences what activating does before it is done', async () => {
    const { container, calls } = await renderRates([DRAFT, CURRENT], true, {
      '/api/rates/cards/c-draft/activation-preview': {
        card: DRAFT,
        shortened: {
          id: 'c-now',
          name: 'Tarieven lopend',
          old_valid_to: null,
          new_valid_to: '2099-07-14',
        },
        impact: {
          ...NO_IMPACT,
          budget_lines_changed: 14,
          budget_difference_cents: 4200000,
          allocations_changed: 9,
          open_difference_cents: 3100000,
        },
      },
    });
    const link = [...container.querySelectorAll('nldd-table nldd-link')].find(
      (el) => el.getAttribute('text') === DRAFT.name,
    );
    fireEvent.click(link as Element);
    const activate = () =>
      [...container.querySelectorAll('nldd-title nldd-button')].find(
        (el) => el.getAttribute('text') === 'Activeer',
      );
    await waitFor(() => expect(activate()).toBeDefined());
    fireEvent.click(activate() as Element);
    await waitFor(() => expect(openSheet(`Activeer ${DRAFT.name}`)).toBeDefined());
    const sheet = openSheet(`Activeer ${DRAFT.name}`) as HTMLElement;
    await waitFor(() => expect(sheet.querySelectorAll('nldd-text').length).toBeGreaterThan(2));
    const sentences = [...sheet.querySelectorAll('nldd-text')].map((el) => plain(el.textContent));
    expect(sentences).toContain("De tarievenkaart 'Tarieven lopend' eindigt op 14 jul 2099.");
    expect(sentences).toContain(
      '14 begrotingsregels krijgen vanaf 15 jul 2099 een ander begroot bedrag, samen € 42.000 hoger.',
    );
    expect(sentences).toContain('Afgesloten maanden veranderen niet.');
    // Looking activated nothing.
    expect(calls.every((url) => !url.endsWith('/activate'))).toBe(true);
  });
});

describe('the sentences about what changes', () => {
  it('names the naverrekening for months already delivered', () => {
    const sentences = impactSentences(
      {
        ...NO_IMPACT,
        allocations_changed: 1,
        open_difference_cents: 150000,
        correction_cents: 60000,
        reaches_into_the_past: true,
        assignments: [
          {
            assignment_id: 'a-1',
            assignment_name: 'Opdracht Alfa',
            open_difference_cents: 150000,
            closed_difference_cents: 0,
            correction_cents: 60000,
            months: [
              {
                month: '2026-07',
                state: 'invoiced',
                before_cents: 1500000,
                after_cents: 1530000,
                difference_cents: 30000,
                invoice_number: 'F-26-014',
              },
              {
                month: '2026-08',
                state: 'delivered',
                before_cents: 1500000,
                after_cents: 1530000,
                difference_cents: 30000,
                invoice_number: null,
              },
              {
                month: '2026-09',
                state: 'open',
                before_cents: 1500000,
                after_cents: 1530000,
                difference_cents: 30000,
                invoice_number: null,
              },
            ],
          },
        ],
      },
      '2026-07-01',
    ).map(plain);
    expect(sentences).toContain(
      '1 inzet krijgt vanaf 1 jul 2026 een ander bedrag. In de maanden die nog open zijn is dat samen € 1.500 hoger.',
    );
    expect(sentences).toContain(
      'Voor maanden die al zijn aangeleverd ontstaat een naverrekening van samen € 600 hoger. De aanlevering zelf blijft zoals ze was.',
    );
    expect(sentences).toContain(
      'Opdracht Alfa: juli 2026 (gefactureerd, factuur F-26-014) € 300 hoger; augustus 2026 (aangeleverd) € 300 hoger.',
    );
    expect(sentences.join(' ')).not.toContain('september');
  });

  it('says lower for a negative difference and flags months that cannot be priced', () => {
    const sentences = impactSentences(
      {
        ...NO_IMPACT,
        budget_lines_changed: 1,
        budget_difference_cents: -25000,
        unpriced_months: 2,
      },
      '2027-01-01',
    ).map(plain);
    expect(sentences[0]).toBe(
      '1 begrotingsregel krijgt vanaf 1 jan 2027 een ander begroot bedrag, samen € 250 lager.',
    );
    expect(sentences.at(-1)).toContain('2 maanden zijn daarna niet meer te prijzen');
  });

  it('says so when a start date lies in the past', () => {
    const sentences = activationSentences({
      card: { ...DRAFT, valid_from: '2020-01-01' } as never,
      shortened: null,
      impact: { ...NO_IMPACT, reaches_into_the_past: true },
    });
    expect(sentences).toContain('De begindatum ligt in het verleden.');
  });
});

describe('validity', () => {
  it('writes a period the way it is said', () => {
    expect(validityText('2026-01-01', '2026-06-30')).toBe('geldig van 1 jan 2026 t/m 30 jun 2026');
    expect(validityText('2026-07-01', null)).toBe('geldig vanaf 1 jul 2026');
  });

  it('places a card in time from its period, not from a year', () => {
    const card = { status: 'active' as const, valid_from: '2026-07-01', valid_to: null };
    expect(momentOf(card, '2026-06-30')).toBe('coming');
    expect(momentOf(card, '2026-07-01')).toBe('now');
    expect(momentOf({ ...card, valid_to: '2026-12-31' }, '2027-01-01')).toBe('past');
    expect(momentOf({ ...card, status: 'draft' }, '2026-08-01')).toBe('draft');
  });

  it('proposes the first day of next year', () => {
    expect(firstDayOfNextYear('2026-10-08')).toBe('2027-01-01');
  });
});

describe('where the rate cards live', () => {
  it('is under Beheer, not in the main navigation', () => {
    expect(APP_ROUTES.map((route) => route.title)).not.toContain('Tarieven');
  });

  it.each(['/beheer/tarieven', '/tarieven'])('shows the screen at %s', async (path) => {
    mockApi({ '/api/rates/cards': { items: [], may_manage: false, default_increase_pct: '5.00' } });
    const { container } = renderApp(<AppRoutes />, { path });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain('Er is nog geen tarievenkaart'),
    );
    expect(container.querySelector('h1')?.textContent).toBe('Tarieven');
  });
});
