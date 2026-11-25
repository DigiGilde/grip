import { act, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { referenceText, signalText, varianceText, varianceWord } from '../financeText';
import { FIGURES, PERMISSIONS, allText, assignment, finance, mockApi, plain } from '../testing';
import { BUDGET, CARDS, renderBudgetPart } from './testing';

afterEach(() => vi.unstubAllGlobals());

const QUOTES = { quotes: [] };

function renderStand(data = finance(), shell = assignment(), budget: unknown = BUDGET) {
  const fetchMock = mockApi({
    '/api/assignments/a1/financial': data,
    '/api/assignments/a1/budget': budget,
    '/api/assignments/a1/quotes': QUOTES,
    '/api/rates/cards': CARDS,
  });
  const view = renderBudgetPart(shell);
  return { ...view, fetchMock };
}

const asked = (fetchMock: ReturnType<typeof vi.fn>) =>
  (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));

const STAND = 'nldd-table[accessible-label^="Stand per"]';

const standOf = async (container: HTMLElement) => {
  await waitFor(() => expect(container.querySelector(STAND)).not.toBeNull());
  return container.querySelector(STAND) as HTMLElement;
};

const cells = (root: Element, selector: string) =>
  [...root.querySelectorAll(selector)].map((cell) => cell.getAttribute('text'));

const openSheet = () => document.querySelector('nldd-sheet[open]');

/** The rows of a table without its head, in order. */
const rowsOf = (table: Element) =>
  [...table.children].filter((row) => row.getAttribute('slot') !== 'header');

const isAfter = (first: Element, second: Element) =>
  Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);

const LEZER = { permissions: PERMISSIONS.lezer };
const READER_BUDGET = {
  ...BUDGET,
  can_edit: false,
  lines: BUDGET.lines.map(({ id, assignment_id, description, kind, position, rate_category }) => ({
    id,
    assignment_id,
    description,
    kind,
    position,
    rate_category,
  })),
};

describe('the state of the budget', () => {
  it('names the state of the money in the columns', async () => {
    const { container } = renderStand();
    const table = await standOf(container);
    expect(cells(table, 'nldd-table-row[slot="header"] nldd-text-cell')).toEqual([
      'Regel',
      'Begroot',
      'Gerealiseerde inzet',
      'Nog gepland',
      'Kosten',
      'Verwacht totaal',
      'Afwijking',
      'Uitputting',
    ]);
  });

  it('says under Uitputting in the total row which amount the share is of', async () => {
    const { container } = renderStand();
    const table = await standOf(container);
    const notes = [...table.querySelectorAll('nldd-text-cell')]
      .map((cell) => plain(cell.getAttribute('supporting-text')))
      .filter((note) => note.endsWith(' gerealiseerd'));
    expect(notes).toEqual(['€ 30.000 gerealiseerd']);
  });

  it('says FTE and scale under the name of a line, and the cause of a rate difference', async () => {
    const base = finance();
    const line = {
      ...base.lines[0]!,
      rate_difference_notes: ['gepromoveerd per 1 juli 2026: vanaf dan categorie C'],
    };
    const { container } = renderStand(finance({ lines: [line] }));
    const table = await standOf(container);
    await waitFor(() =>
      expect(
        table.querySelector('nldd-text-cell[row-header]')?.getAttribute('supporting-text'),
      ).toBe(
        '0,8 FTE, schaal 14 en 15 (categorie D). Beoogd: Voorbeeld Een, onder voorbehoud. Gepromoveerd per 1 juli 2026: vanaf dan categorie C',
      ),
    );
  });

  it('gives a reader the scale and what the server gives, and no FTE', async () => {
    const { container } = renderStand(finance(), assignment(LEZER), READER_BUDGET);
    const table = await standOf(container);
    await waitFor(() =>
      expect(
        table.querySelector('nldd-text-cell[row-header]')?.getAttribute('supporting-text'),
      ).toBe('Schaal 14 en 15 (categorie D)'),
    );
    expect(allText(table)).not.toContain('FTE');
  });

  it('shows the figures of the service and never its own sums', async () => {
    // Figures that do not add up on purpose: the screen must show them as sent.
    const odd = {
      ...FIGURES,
      expected_total_cents: 12345600,
      variance_cents: 99900,
      variance_pct: '0.5',
    };
    const { container } = renderStand(finance({ totals: odd }));
    const table = await standOf(container);
    const total = rowsOf(table).at(-1) as Element;
    const text = allText(total as HTMLElement);
    expect(text).toContain('**€ 123.456**');
    expect(text).toContain('**€ 999**');
    expect(text).toContain('0,5%, ruimte');
  });

  it('opens on the whole period, with a total row equal to the head', async () => {
    const { container, fetchMock } = renderStand();
    const table = await standOf(container);
    expect(asked(fetchMock)).toContain('/api/assignments/a1/financial?year=all');
    expect(asked(fetchMock).filter((url) => url.includes('/financial?'))).toHaveLength(1);
    const total = rowsOf(table).at(-1) as Element;
    const shown = [...total.querySelectorAll('nldd-text-cell')].map((cell) =>
      plain(cell.getAttribute('text')),
    );
    expect(shown.slice(0, 3)).toEqual(['**Totaal**', '**€ 187.800**', '**€ 27.000**']);
    expect(table.getAttribute('accessible-label')).toBe(
      'Stand per begrotingsregel, de hele looptijd',
    );
  });

  it('says how far the amounts are real, in one quiet line above the table', async () => {
    const { container } = renderStand();
    const table = await standOf(container);
    const line = [...container.querySelectorAll('nldd-text[color="secondary"]')].find((el) =>
      el.textContent?.startsWith('Hele looptijd'),
    ) as Element;
    expect(plain(line.textContent)).toBe(
      'Hele looptijd, 1 jan 2026 t/m 31 dec 2026. Stand t/m februari 2026 (laatst afgesloten maand).',
    );
    expect(isAfter(line, table)).toBe(true);
  });

  it('says one quiet line about the signed quote and how it differs', async () => {
    const { container } = renderStand();
    await standOf(container);
    expect(allText(container)).toContain(
      'Offerte met akkoord: € 190.000, € 2.200 hoger dan de begroting.',
    );
  });

  it('says nothing about a quote that is not there, or about being equal', async () => {
    const base = finance();
    const none = { ...base.key_figures, agreed_cents: null, agreed_minus_budgeted_cents: null };
    const { container } = renderStand(finance({ key_figures: none }));
    await standOf(container);
    expect(allText(container)).not.toContain('Offerte met akkoord');
    vi.unstubAllGlobals();
    const equal = { ...base.key_figures, agreed_minus_budgeted_cents: 0 };
    const other = renderStand(finance({ key_figures: equal }));
    await standOf(other.container);
    expect(allText(other.container)).toContain('Offerte met akkoord: € 190.000.');
    expect(allText(other.container)).not.toContain('hoger dan');
  });

  it('leaves delivery and invoices to the part that closes and bills', async () => {
    const { container } = renderStand();
    await standOf(container);
    const text = allText(container);
    expect(text).not.toContain('Aangeleverd');
    expect(text).not.toContain('Nog te factureren');
    expect(container.querySelector('dl')).toBeNull();
  });

  it('lists the signals under the table, an overrun in words', async () => {
    const { container } = renderStand(
      finance({
        signals: [
          {
            kind: 'overrun',
            budget_line_id: 'l1',
            description: 'Productmanager',
            amount_cents: 500000,
            pct: '2.9',
            count: null,
            months: [],
          },
          {
            kind: 'months_not_closed',
            budget_line_id: null,
            description: null,
            amount_cents: null,
            pct: null,
            count: 2,
            months: ['2026-03-01', '2026-04-01'],
          },
        ],
      }),
    );
    await waitFor(() => expect(container.querySelectorAll('.signal').length).toBe(2));
    const signals = [...container.querySelectorAll('.signal')];
    const said = signals.map((signal) => plain(signal.querySelector('nldd-text')?.textContent));
    expect(said[0]).toContain('Overschrijding op Productmanager');
    expect(said[0]).toContain('€ 5.000');
    expect(said[1]).toContain('2 maanden zijn voorbij en nog niet afgesloten');
    expect(signals[0]).toHaveClass('signal-critical');
    const table = container.querySelector(STAND) as Element;
    expect(isAfter(table, signals[0]!)).toBe(true);
    const support = container.querySelector('nldd-list[type="tree"]') as Element;
    expect(isAfter(signals[1]!, support)).toBe(true);
  });

  it('keeps the detail behind a row that opens, with persons and cost coverage', async () => {
    const { container } = renderStand();
    await waitFor(() => expect(container.querySelector('nldd-list[type="tree"]')).not.toBeNull());
    const row = container.querySelector('nldd-list[type="tree"] > nldd-list-item') as HTMLElement;
    expect(row).not.toHaveAttribute('expanded');
    const children = [...row.querySelectorAll('nldd-list-item[slot="children"]')];
    expect(children).toHaveLength(2);
    expect(allText(children[0] as HTMLElement)).toContain('Voorbeeld Een');
    expect(allText(children[0] as HTMLElement)).toContain('€ 162.000');
    expect(allText(children[1] as HTMLElement)).toContain('Hostingcontract');
    expect(allText(children[1] as HTMLElement)).toContain(
      '€ 3.000 gerealiseerd, € 1.500 ingeschat',
    );
    act(() => {
      row.dispatchEvent(new Event('click', { bubbles: true }));
    });
    await waitFor(() => expect(row).toHaveAttribute('expanded'));
  });

  it('shows how the costs split in the column and in the total', async () => {
    const { container } = renderStand();
    const table = await standOf(container);
    const split = [...table.querySelectorAll('nldd-text-cell')].filter(
      (cell) =>
        plain(cell.getAttribute('supporting-text')) === '€ 3.000 gerealiseerd, € 1.500 ingeschat',
    );
    expect(split).toHaveLength(2);
  });

  it('says when amounts per person are withheld', async () => {
    const base = finance();
    const line = { ...base.lines[0]!, persons: [], persons_hidden: 2 };
    const { container } = renderStand(finance({ lines: [line] }), assignment(LEZER), READER_BUDGET);
    await waitFor(() => expect(allText(container)).toContain('2 personen zit in het totaal'));
    expect(allText(container)).not.toContain('Voorbeeld Een');
  });

  it('shows the months with closed ones marked, and the chart with its table', async () => {
    const { container } = renderStand();
    await waitFor(() =>
      expect(
        container.querySelector('nldd-table[accessible-label^="Inzet per maand"]'),
      ).not.toBeNull(),
    );
    const table = container.querySelector(
      'nldd-table[accessible-label^="Inzet per maand"]',
    ) as HTMLElement;
    const text = allText(table);
    expect(text).toContain('Afgesloten');
    expect(text).toContain('Open');
    expect(text).toContain('Onder de begroting');
    expect(text).toContain('Januari 2026');
    expect(container.querySelector('svg')).not.toBeNull();
    // Begroot adds up to less here than in the table above; the page says why.
    expect(allText(container)).toContain('€ 15.000 van de begroting');
    const support = container.querySelector('nldd-list[type="tree"]') as Element;
    expect(isAfter(support, table)).toBe(true);
  });

  it('offers both tables as CSV under the months, for the chosen period', async () => {
    const { container } = renderStand();
    await standOf(container);
    const links = [...container.querySelectorAll('nldd-link[href*="/financial/csv"]')];
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/api/assignments/a1/financial/csv?year=all&section=lines',
      '/api/assignments/a1/financial/csv?year=all&section=months',
    ]);
    const months = container.querySelector('nldd-table[accessible-label^="Inzet per maand"]');
    expect(isAfter(months as Element, links[0]!)).toBe(true);
  });

  it('has no list of months, chart or downloads without lines and months', async () => {
    const { container } = renderStand(finance({ lines: [], months: [], totals: null }));
    await waitFor(() =>
      expect(container.querySelector('nldd-inline-dialog')?.getAttribute('text')).toBe(
        'Deze opdracht heeft nog geen begrotingsregels',
      ),
    );
    expect(container.querySelector('nldd-table')).toBeNull();
    expect(container.querySelector('nldd-link[href*="/financial/csv"]')).toBeNull();
    expect(container.querySelector('svg')).toBeNull();
  });

  it('says that a line could not be priced, and shows the total of the service', async () => {
    const base = finance();
    const line = { ...base.lines[0]!, figures: null, pricing_error: 'Geen tarief voor 2031' };
    const { container } = renderStand(finance({ lines: [line], totals: null }));
    const table = await standOf(container);
    expect(table.querySelector('nldd-text-cell[text="Niet berekend"]')).not.toBeNull();
    expect(allText(table)).toContain('Geen tarief voor 2031');
  });

  it('warns about a fixed amount outside the period, where the way to change it is', async () => {
    const fixed = {
      ...BUDGET.lines[0]!,
      id: 'l2',
      description: 'Hosting',
      kind: 'fixed',
      year: 2031,
    };
    const { container } = renderStand(finance(), assignment(), { ...BUDGET, lines: [fixed] });
    await waitFor(() =>
      expect(container.querySelector('nldd-banner[variant="warning"]')).not.toBeNull(),
    );
    const banner = container.querySelector('nldd-banner[variant="warning"]') as Element;
    expect(banner.getAttribute('text')).toBe(
      'Hosting staat op 2031, buiten de looptijd van de opdracht',
    );
    expect(banner.getAttribute('supporting-text')).toContain('of wijzig de looptijd.');
    expect(banner.getAttribute('supporting-text')).not.toContain('Overzicht');
  });
});

describe('everything that stood apart on two tabs', () => {
  it('has its one place, in this order', async () => {
    const base = finance();
    const { container } = renderStand(
      finance({
        lines: [{ ...base.lines[0]!, rate_difference_notes: ['tariefwijziging per 1 juli 2026'] }],
        signals: [
          {
            kind: 'overrun',
            budget_line_id: 'l1',
            description: 'Productmanager',
            amount_cents: 500000,
            pct: '2.9',
            count: null,
            months: [],
          },
        ],
      }),
    );
    const table = await standOf(container);
    await waitFor(() => expect(allText(table)).toContain('Tariefwijziging per 1 juli 2026'));
    const inOrder = [
      container.querySelector('nldd-button[text="Wijzig de looptijd"]'),
      table,
      container.querySelector('.signal'),
      container.querySelector('nldd-list[type="tree"]'),
      container.querySelector('svg'),
      container.querySelector('nldd-table[accessible-label^="Inzet per maand"]'),
      container.querySelector('nldd-link[href$="section=lines"]'),
      container.querySelector('nldd-link[href$="section=months"]'),
    ];
    inOrder.forEach((element) => expect(element).not.toBeNull());
    inOrder.slice(1).forEach((element, index) => {
      expect(isAfter(inOrder[index] as Element, element as Element)).toBe(true);
    });
    const text = allText(container);
    expect(text).toContain('Stand t/m februari 2026');
    expect(text).toContain('Offerte met akkoord: € 190.000');
    expect(text).toContain('€ 3.000 gerealiseerd, € 1.500 ingeschat');
    expect(text).toContain('€ 15.000 van de begroting staat hier niet in');
    expect(container.querySelector('nldd-banner')).toBeNull();
    expect(text).not.toContain('nog niet akkoord');
  });
});

describe('the choice of a year', () => {
  const twoYears = { start_date: '2026-07-01', end_date: '2027-06-30' };

  it('is there only when the assignment runs over more than one year', async () => {
    const { container } = renderStand();
    await standOf(container);
    expect(container.querySelector('nldd-dropdown')).toBeNull();
    vi.unstubAllGlobals();
    const other = renderStand(finance(), assignment(twoYears));
    await standOf(other.container);
    const options = [...other.container.querySelectorAll('nldd-dropdown option')];
    expect(options.map((option) => option.textContent)).toEqual(['2026', '2027', 'Hele looptijd']);
    expect(other.container.querySelector('nldd-dropdown select')).toHaveValue('all');
  });

  it('is not there without a known period', async () => {
    const { container } = renderStand(finance(), assignment({ start_date: null, end_date: null }));
    await standOf(container);
    expect(container.querySelector('nldd-dropdown')).toBeNull();
  });

  it('asks the server for that year, and names it in the line and the downloads', async () => {
    const { container, fetchMock } = renderStand(finance(), assignment(twoYears));
    await standOf(container);
    fireEvent.change(container.querySelector('nldd-dropdown select') as HTMLSelectElement, {
      target: { value: '2027' },
    });
    await waitFor(() =>
      expect(asked(fetchMock)).toContain('/api/assignments/a1/financial?year=2027'),
    );
    const table = await standOf(container);
    expect(table.getAttribute('accessible-label')).toBe('Stand per begrotingsregel, 2027');
    const text = allText(container);
    expect(text).toContain('Over 2027. Stand t/m februari 2026 (laatst afgesloten maand).');
    expect(text).toContain('Offerte met akkoord over de hele looptijd: € 190.000');
    expect(
      container.querySelector(
        'nldd-link[href="/api/assignments/a1/financial/csv?year=2027&section=lines"]',
      ),
    ).not.toBeNull();
  });
});

describe('changing the budget from the state', () => {
  it('opens the sheet of the line from its row, for who may change it', async () => {
    const { container } = renderStand();
    const table = await standOf(container);
    await waitFor(() => expect(table.querySelector('nldd-link')).not.toBeNull());
    expect(openSheet()).toBeNull();
    act(() => {
      rowsOf(table)[0]!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await waitFor(() => expect(openSheet()).not.toBeNull());
    expect(openSheet()?.querySelector('nldd-top-title-bar')?.getAttribute('text')).toBe(
      'Productmanager bewerken',
    );
    expect(openSheet()?.querySelector('nldd-form-field[label="Omvang in FTE"]')).not.toBeNull();
  });

  it('lets a keyboard reach the name, which says what it does', async () => {
    const { container } = renderStand();
    const table = await standOf(container);
    await waitFor(() => expect(table.querySelector('nldd-link')).not.toBeNull());
    const name = table.querySelector('nldd-link') as Element;
    expect(name.getAttribute('text')).toBe('Productmanager');
    expect(name.getAttribute('accessible-label')).toBe('Bewerk Productmanager');
    act(() => {
      name.dispatchEvent(new Event('click', { cancelable: true }));
    });
    await waitFor(() => expect(openSheet()).not.toBeNull());
  });

  it('opens no sheet for a reader, who reads on in the detail', async () => {
    const { container } = renderStand(finance(), assignment(LEZER), READER_BUDGET);
    const table = await standOf(container);
    await waitFor(() =>
      expect(
        table.querySelector('nldd-text-cell[row-header]')?.getAttribute('supporting-text'),
      ).toBe('Schaal 14 en 15 (categorie D)'),
    );
    expect(table.querySelector('nldd-link')).toBeNull();
    expect(table.querySelector('nldd-icon-button')).toBeNull();
    expect(table.getAttribute('columns')).not.toContain('48px');
    act(() => {
      rowsOf(table)[0]!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.querySelector('nldd-sheet')).toBeNull();
    expect(container.querySelector('nldd-button[appearance="primary"]')).toBeNull();
    expect(container.querySelector('nldd-list[type="tree"]')).not.toBeNull();
  });

  it('keeps the rest of a row behind one quiet menu, and removing asks first', async () => {
    const { container } = renderStand();
    const table = await standOf(container);
    await waitFor(() => expect(table.querySelector('nldd-icon-button')).not.toBeNull());
    const more = table.querySelector('nldd-icon-button') as Element;
    expect(more.getAttribute('accessible-label')).toBe('Meer acties voor Productmanager');
    expect(
      [...more.querySelectorAll('nldd-menu-item')].map((item) => item.getAttribute('text')),
    ).toEqual(['Bekijk inzet', 'Verwijder']);
    act(() => {
      more.querySelector('nldd-menu-item[text="Verwijder"]')?.dispatchEvent(new Event('select'));
    });
    await waitFor(() => expect(document.querySelector('nldd-modal-dialog[open]')).not.toBeNull());
    expect(document.querySelector('nldd-modal-dialog')?.getAttribute('supporting-text')).toContain(
      'De reservering van Voorbeeld Een vervalt ook.',
    );
  });

  it('adds a line from the one button in the head', async () => {
    const { container } = renderStand();
    await standOf(container);
    const buttons = [...container.querySelectorAll('nldd-button[appearance="primary"]')];
    expect(buttons.map((button) => button.getAttribute('text'))).toEqual([
      'Nieuwe begrotingsregel',
    ]);
    expect(buttons[0]?.closest('.thing-action')).not.toBeNull();
    act(() => {
      buttons[0]?.dispatchEvent(new Event('click'));
    });
    await waitFor(() => expect(openSheet()).not.toBeNull());
    expect(openSheet()?.querySelector('nldd-top-title-bar')?.getAttribute('text')).toBe(
      'Nieuwe begrotingsregel',
    );
  });

  it('says what a change means after a signature, in the sheet and not on the page', async () => {
    const fetchMock = mockApi({
      '/api/assignments/a1/financial': finance(),
      '/api/assignments/a1/budget': BUDGET,
      '/api/assignments/a1/quotes': {
        quotes: [{ status: 'accepted', reference: 'VG-2026-0002', issued_at: '2026-01-02' }],
      },
      '/api/rates/cards': CARDS,
    });
    const { container } = renderBudgetPart(assignment());
    const table = await standOf(container);
    await waitFor(() => expect(table.querySelector('nldd-link')).not.toBeNull());
    expect(allText(container)).not.toContain('is de afspraak');
    expect(asked(fetchMock).some((url) => url.includes('/quotes'))).toBe(false);
    act(() => {
      rowsOf(table)[0]!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await waitFor(() =>
      expect(allText(openSheet() as HTMLElement)).toContain(
        'De getekende offerte (VG-2026-0002) is de afspraak.',
      ),
    );
    expect(allText(container)).not.toContain('is de afspraak');
  });

  it('changes the period from the bar, for who may', async () => {
    const { container } = renderStand();
    await standOf(container);
    const button = container.querySelector('nldd-button[text="Wijzig de looptijd"]') as Element;
    expect(button.getAttribute('appearance')).toBe('secondary');
    act(() => {
      button.dispatchEvent(new Event('click'));
    });
    await waitFor(() => expect(openSheet()).not.toBeNull());
    expect(openSheet()?.querySelector('nldd-top-title-bar')?.getAttribute('text')).toBe(
      'Looptijd van de opdracht',
    );
    vi.unstubAllGlobals();
    const reader = renderStand(finance(), assignment(LEZER), READER_BUDGET);
    await standOf(reader.container);
    expect(reader.container.querySelector('nldd-button[text="Wijzig de looptijd"]')).toBeNull();
  });
});

describe('finance wording', () => {
  it('says room, overrun or none', () => {
    expect(varianceWord({ variance_cents: 1 })).toBe('Ruimte');
    expect(varianceWord({ variance_cents: -1 })).toBe('Overschrijding');
    expect(varianceWord({ variance_cents: 0 })).toBe('Geen ruimte');
    expect(plain(varianceText({ variance_cents: -500000, variance_pct: '-2.9' }))).toBe(
      '€ -5.000 (-2,9%)',
    );
    expect(plain(varianceText({ variance_cents: 0, variance_pct: null }))).toBe('€ 0');
  });

  it('says so when no month is closed', () => {
    expect(referenceText(null)).toContain('nog geen maand afgesloten');
  });

  it('names free room against the threshold', () => {
    const text = signalText(
      {
        kind: 'free_room',
        budget_line_id: 'l1',
        description: 'Ontwerper',
        amount_cents: 2000000,
        pct: '18.5',
        count: null,
        months: [],
      },
      '10',
    );
    expect(text.variant).toBe('neutral');
    expect(plain(text.text)).toContain('Vrije ruimte op Ontwerper');
    expect(text.text).toContain('18,5%');
    expect(text.text).toContain('drempel van 10%');
  });
});

describe('a line without inzet and the way to the report', () => {
  const NOTHING = {
    ...FIGURES,
    realised_cents: 0,
    planned_cents: 0,
    costs_cents: 0,
    expected_total_cents: 0,
    variance_cents: 18780000,
    variance_pct: '100.0',
    realised_pct: '0.0',
  };

  it('says that nothing is planned on a personnel line, not 100% room, and keeps room on a fixed line', async () => {
    const base = finance();
    const personnel = { ...base.lines[0]!, figures: NOTHING };
    const fixed = {
      ...base.lines[0]!,
      budget_line_id: 'l2',
      description: 'Hosting',
      kind: 'fixed',
      figures: NOTHING,
    };
    const { container } = renderStand(finance({ lines: [personnel, fixed], totals: FIGURES }));
    const table = await standOf(container);
    const [first, second] = rowsOf(table);
    expect(allText(first as HTMLElement)).toContain('Niets gepland');
    expect(allText(first as HTMLElement)).not.toContain('Nog geen inzet gepland');
    expect(allText(first as HTMLElement)).not.toContain('ruimte');
    expect(allText(second as HTMLElement)).not.toContain('Niets gepland');
    expect(allText(second as HTMLElement)).toContain('100%, ruimte');
  });

  it('links to the report of this assignment while the part has no row', async () => {
    const { container } = renderStand();
    await standOf(container);
    const link = container.querySelector('nldd-link[href="/opdrachten/a1/rapport"]');
    expect(link?.getAttribute('text')).toBe('Rapport van deze opdracht');
  });

  it('leaves that link out once the report has its row', async () => {
    mockApi({
      '/api/assignments/a1/financial': finance(),
      '/api/assignments/a1/budget': BUDGET,
      '/api/assignments/a1/quotes': QUOTES,
      '/api/rates/cards': CARDS,
    });
    const withRow = renderBudgetPart(assignment(), [
      { key: 'budget', label: 'Begroting', notice: null },
      { key: 'report', label: 'Eindrapport', notice: null },
    ]);
    await standOf(withRow.container);
    expect(withRow.container.querySelector('nldd-link[href$="/rapport"]')).toBeNull();
  });
});
