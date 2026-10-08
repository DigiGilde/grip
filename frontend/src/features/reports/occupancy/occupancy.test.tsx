import { fireEvent, screen, within } from '@testing-library/react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { renderApp } from '@/test/utils';
import type { Occupancy, OccupancyCell, OccupancyMonth, PersonOccupancy } from '../api';
import { occupancyTiles } from './figures';
import { Heatmap } from './Heatmap';
import { describeCell, freeSummary, sortPersons } from './model';
import { OccupancyBlock } from './OccupancyBlock';
import { cellState, fillLevel } from './scale';
import { groupPersons } from './view';

const MONTHS = Array.from({ length: 12 }, (_, index) => `2026-${String(index + 1).padStart(2, '0')}`);

function cell(month: string, overrides: Partial<OccupancyCell> = {}): OccupancyCell {
  return {
    month,
    available: true,
    pct: '0',
    tentative_pct: '0',
    established: false,
    parts: [],
    ...overrides,
  };
}

function person(
  id: string,
  name: string,
  byMonth: Record<string, Partial<OccupancyCell>>,
  extra: Partial<PersonOccupancy> = {},
): PersonOccupancy {
  return {
    person_id: id,
    person_name: name,
    average_pct: '50',
    over_months: [],
    now_pct: '50',
    idle_ahead: false,
    last_inzet_end: '2026-12-31',
    cells: MONTHS.map((month) => cell(month, byMonth[month])),
    ...extra,
  };
}

const month = (name: string, pct: string | null = '50'): OccupancyMonth => ({
  month: name,
  allocated_fte: '1',
  tentative_fte: '0',
  available_fte: '2',
  free_fte: '1',
  pct,
  under: 1,
  full: 0,
  over: 0,
});

const YEAR_MONTHS = MONTHS.map((name) => month(name));

// Fictional people. Mila: established in July, overbooked in September with
// a tentative part, not deployable in January. Cas: half the year at 50.
const MILA = person(
  'p1',
  'Mila Medewerker',
  {
    '2026-01': { available: false },
    '2026-07': {
      pct: '80',
      established: true,
      parts: [
        {
          assignment_id: 'a1',
          assignment_name: 'Opdracht Alfa',
          pct: '80',
          tentative: false,
          verbally_agreed: false,
          established: true,
        },
      ],
    },
    '2026-09': {
      pct: '130',
      tentative_pct: '30',
      parts: [
        {
          assignment_id: 'a1',
          assignment_name: 'Opdracht Alfa',
          pct: '100',
          tentative: false,
          verbally_agreed: false,
          established: false,
        },
        { pct: '30', tentative: true, verbally_agreed: true, established: false },
      ],
    },
    '2026-10': { pct: '100' },
  },
  { average_pct: '65', over_months: ['2026-09'], now_pct: '100' },
);
const CAS = person('p2', 'Cas Collega', { '2026-10': { pct: '50' } }, { average_pct: '25' });
// Deployable, without inzet in the year and in the coming months.
const NOOR = person(
  'p4',
  'Noor Nieuw',
  {},
  { average_pct: '0', now_pct: '0', idle_ahead: true, last_inzet_end: '2025-11-30' },
);
// Had inzet earlier in the year, none in the coming months.
const STEF = person(
  'p5',
  'Stef Stil',
  { '2026-03': { pct: '100' } },
  { average_pct: '8', now_pct: '0', idle_ahead: true, last_inzet_end: '2026-03-31' },
);
const ANNA = person(
  'p3',
  'Anna Analist',
  { '2026-10': { pct: '20' } },
  { average_pct: '10', now_pct: '20' },
);

const SUMMARY = {
  person_count: 4,
  average_pct: '33.3',
  over_count: 1,
  over_months: ['2026-09'],
  current_month: '2026-10',
  window: [
    { ...month('2026-10'), free_fte: '1.3', tentative_fte: '0.3' },
    { ...month('2026-11'), free_fte: '2' },
    { ...month('2026-12'), free_fte: '2.5' },
    { ...month('2027-01'), free_fte: '3' },
  ],
  idle_count: 1,
};

const OCCUPANCY: Occupancy = {
  scope: 'own',
  summary: SUMMARY,
  months: YEAR_MONTHS,
  persons: [MILA, CAS, ANNA, NOOR],
  not_deployable: [
    { person_id: 'p8', person_name: 'Bea Beheer' },
    { person_id: 'p9', person_name: 'Lex Lezer' },
  ],
};

function renderHeatmap(persons = [MILA, CAS], currentMonth = '2026-10') {
  const selections: unknown[] = [];
  const utils = renderApp(
    <Heatmap
      label="Bezetting per persoon en maand in 2026, in procenten"
      persons={persons}
      months={YEAR_MONTHS}
      currentMonth={currentMonth}
      selected={null}
      onSelect={(next) => selections.push(next)}
    />,
  );
  return { ...utils, selections };
}

const cellOf = (container: HTMLElement, personId: string, monthName: string) =>
  container.querySelector<HTMLElement>(`tr[data-person="${personId}"] td[data-month="${monthName}"]`)!;

describe('the scale', () => {
  it('tells not deployable from deployable and empty', () => {
    expect(cellState(false, 0)).toBe('unavailable');
    expect(cellState(true, 0)).toBe('empty');
    expect(cellState(true, 100)).toBe('filled');
    expect(cellState(true, 100.1)).toBe('over');
  });

  it('has four fill steps up to 100 percent', () => {
    expect([1, 25, 26, 50, 51, 75, 76, 100].map(fillLevel)).toEqual([1, 1, 2, 2, 3, 3, 4, 4]);
  });
});

describe('describeCell', () => {
  it('says every state in words', () => {
    expect(describeCell(cell('2026-01', { available: false }))).toBe('niet inzetbaar');
    expect(describeCell(cell('2026-02'))).toBe('geen inzet');
    expect(describeCell(cell('2026-07', { pct: '80', established: true }))).toBe('80%, vastgesteld');
    expect(describeCell(cell('2026-09', { pct: '130', tentative_pct: '30' }))).toBe(
      '130%, boven 100%, waarvan 30% onder voorbehoud, gepland',
    );
    expect(describeCell(cell('2026-05', { pct: '100', tentative_pct: '100' }))).toBe(
      '100%, onder voorbehoud, gepland',
    );
  });
});

describe('sortPersons', () => {
  it('puts the overbooked first, then whoever has most room', () => {
    expect(sortPersons([CAS, ANNA, MILA], 'problems').map((p) => p.person_name)).toEqual([
      'Mila Medewerker',
      'Anna Analist',
      'Cas Collega',
    ]);
  });

  it('sorts by name on request and leaves the input alone', () => {
    const input = [MILA, CAS, ANNA];
    expect(sortPersons(input, 'name').map((p) => p.person_name)).toEqual([
      'Anna Analist',
      'Cas Collega',
      'Mila Medewerker',
    ]);
    expect(input[0]).toBe(MILA);
  });
});

describe('Heatmap', () => {
  it('is a table: a header per month and per person, every value as text', () => {
    const { container } = renderHeatmap();
    const grid = screen.getByRole('grid', {
      name: 'Bezetting per persoon en maand in 2026, in procenten',
    });
    const columns = within(grid).getAllByRole('columnheader');
    expect(columns.map((header) => header.getAttribute('abbr') ?? header.textContent)).toEqual([
      'Verstreken',
      'Lopend en komend',
      'Persoon',
      ...MONTHS.map((_, index) =>
        [
          'januari',
          'februari',
          'maart',
          'april',
          'mei',
          'juni',
          'juli',
          'augustus',
          'september',
          'oktober',
          'november',
          'december',
        ][index] + ' 2026',
      ),
      'Gemiddeld',
    ]);
    expect(
      within(grid)
        .getAllByRole('rowheader')
        .map((header) => header.textContent),
    ).toEqual([expect.stringContaining('Mila Medewerker'), 'Cas Collega', 'Samen']);
    // A name is the way to the Inzet board of that person.
    expect(container.querySelector('tr[data-person="p2"] th a')).toHaveAttribute(
      'href',
      '/inzet?persoon=p2',
    );
    for (const header of container.querySelectorAll('tbody th')) {
      expect(header).toHaveAttribute('scope', 'row');
    }
    expect(cellOf(container, 'p1', '2026-07')).toHaveTextContent('80%, vastgesteld');
    expect(cellOf(container, 'p1', '2026-01')).toHaveTextContent('niet inzetbaar');
    expect(cellOf(container, 'p1', '2026-02')).toHaveTextContent('geen inzet');
  });

  it('gives each state its own treatment', () => {
    const { container } = renderHeatmap();
    const mark = (monthName: string) =>
      cellOf(container, 'p1', monthName).querySelector('.grip-occ__cell')!;

    // Not deployable and deployable-but-empty are different states.
    expect(mark('2026-01')).toHaveAttribute('data-state', 'unavailable');
    expect(mark('2026-02')).toHaveAttribute('data-state', 'empty');
    // A zero is not printed: the cell shows no number.
    expect(mark('2026-02').querySelector('.grip-occ__value')).toBeNull();
    expect(mark('2026-01').querySelector('.grip-occ__value')).toBeNull();

    // The fill carries the value; the number is there, small.
    expect(mark('2026-07')).toHaveAttribute('data-state', 'filled');
    expect(mark('2026-07')).toHaveAttribute('data-level', '4');
    expect(mark('2026-07').querySelector('.grip-occ__value')).toHaveTextContent('80%');
    expect(cellOf(container, 'p2', '2026-10').querySelector('.grip-occ__cell')).toHaveAttribute(
      'data-level',
      '2',
    );

    // Above 100 percent is a state of its own, with a mark in the text.
    expect(mark('2026-09')).toHaveAttribute('data-state', 'over');
    expect(mark('2026-09')).not.toHaveAttribute('data-level');
    // Over 100%: the fixed attention icon stands before the number.
    expect(mark('2026-09').querySelector('.grip-occ__value')).toHaveTextContent('130%');
    expect(mark('2026-09').querySelector('.grip-occ__value nldd-icon')).not.toBeNull();

    // Established carries a dot, tentative stripes over its share.
    expect(mark('2026-07').querySelector('.grip-occ__established')).not.toBeNull();
    expect(mark('2026-09').querySelector('.grip-occ__established')).toBeNull();
    const stripes = mark('2026-09').querySelector<HTMLElement>('.grip-occ__tentative')!;
    expect(Number.parseFloat(stripes.style.width)).toBeCloseTo(23.08, 1);
    expect(mark('2026-07').querySelector('.grip-occ__tentative')).toBeNull();
  });

  it('flags an overbooked person in the row header, in words', () => {
    const { container } = renderHeatmap();
    expect(container.querySelector('tr[data-person="p1"] th')).toHaveTextContent(
      'Boven 100% in 1 maand',
    );
    expect(container.querySelector('tr[data-person="p2"] th')).toHaveTextContent(/^Cas Collega$/);
  });

  it('marks the current month and what lies behind it', () => {
    const { container } = renderHeatmap();
    const now = container.querySelector('thead th[aria-current="date"]')!;
    expect(now).toHaveAttribute('abbr', 'oktober 2026');
    expect(now).toHaveTextContent('nu');
    expect(container.querySelectorAll('thead th[aria-current]')).toHaveLength(1);
    expect(cellOf(container, 'p1', '2026-10')).toHaveClass('grip-occ__now');
    expect(container.querySelector('.grip-occ__group')).toHaveTextContent('Verstreken');
  });

  it('marks no month when today is in another year', () => {
    const { container } = renderHeatmap([MILA], '2027-03');
    expect(container.querySelector('thead th[aria-current]')).toBeNull();
    expect(container.querySelector('.grip-occ__group')).toBeNull();
  });

  it('shows the average as a bar with its number, and the totals in the foot', () => {
    const { container } = renderHeatmap();
    const row = container.querySelector('tr[data-person="p1"]')!;
    expect(row.querySelector<HTMLElement>('.grip-occ__bar')!.style.width).toBe('65%');
    expect(row.querySelector('.grip-occ__average-number')).toHaveTextContent('65%');
    expect(container.querySelector('tfoot')).toHaveTextContent('Samen');
    expect(container.querySelectorAll('tfoot td')).toHaveLength(13);
  });

  it('is one tab stop, walked with the arrow keys', () => {
    const { container, selections } = renderHeatmap();
    const stops = () => [...container.querySelectorAll('td[tabindex="0"]')];
    expect(stops()).toHaveLength(1);
    const first = cellOf(container, 'p1', '2026-01');
    expect(first).toHaveAttribute('tabindex', '0');

    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    const second = cellOf(container, 'p1', '2026-02');
    expect(second).toHaveFocus();
    expect(stops()).toEqual([second]);

    fireEvent.keyDown(second, { key: 'ArrowDown' });
    expect(cellOf(container, 'p2', '2026-02')).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: 'End' });
    expect(cellOf(container, 'p2', '2026-12')).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' });
    expect(cellOf(container, 'p2', '2026-12')).toHaveFocus();

    fireEvent.keyDown(document.activeElement!, { key: 'Enter' });
    expect(selections).toEqual([{ personId: 'p2', month: '2026-12' }]);
    fireEvent.click(cellOf(container, 'p1', '2026-09'));
    expect(selections.at(-1)).toEqual({ personId: 'p1', month: '2026-09' });
  });
});

const GROUPS = groupPersons([MILA, CAS, ANNA, NOOR]);

describe('groupPersons', () => {
  it('gives each figure the people it counts', () => {
    const names = (show: keyof typeof GROUPS) => GROUPS[show].map((p) => p.person_name);
    expect(names('met-inzet')).toEqual(['Mila Medewerker', 'Cas Collega', 'Anna Analist']);
    expect(names('zonder-inzet')).toEqual(['Noor Nieuw']);
    expect(names('boven-100')).toEqual(['Mila Medewerker']);
    expect(names('vrij')).toEqual(['Cas Collega', 'Anna Analist', 'Noor Nieuw']);
    expect(names('iedereen')).toHaveLength(4);
  });
});

describe('occupancyTiles', () => {
  it('says the answer before the table, and where each number leads', () => {
    const tiles = occupancyTiles(SUMMARY, 2026, GROUPS);
    expect(tiles.map((tile) => [tile.label, tile.value])).toEqual([
      ['Gemiddelde bezetting 2026', '33,3%'],
      ['Vrij in oktober 2026', '1,3 FTE'],
      ['Boven 100%', '1 persoon'],
      ['Zonder inzet de komende 3 maanden', '1 persoon'],
    ]);
    expect(tiles.map((tile) => tile.target)).toEqual([
      { show: 'iedereen' },
      { show: 'vrij', sort: 'free' },
      { show: 'boven-100', month: '2026-09' },
      { show: 'zonder-inzet' },
    ]);
    expect(tiles[0]?.detail).toBe('van 4 inzetbare mensen');
    // The months are a small row of their own, the reservation a sentence.
    expect(tiles[1]?.months).toEqual([
      { label: 'nov', value: '2' },
      { label: 'dec', value: '2,5' },
      { label: 'jan', value: '3' },
    ]);
    expect(tiles[1]?.detail).toBe('Van de inzet nu is 0,3 FTE onder voorbehoud.');
    expect(tiles[2]).toMatchObject({ attention: 'Te veel ingepland', detail: 'in sep' });
    expect(tiles[3]).toMatchObject({ attention: 'Geen inzet gepland', detail: 'nov t/m jan' });
  });

  it('steps back, and leads nowhere, when there is nothing to show', () => {
    const tiles = occupancyTiles(
      { ...SUMMARY, over_count: 0, over_months: [], idle_count: 0 },
      2026,
      GROUPS,
    );
    expect(tiles[2]).toMatchObject({ value: 'Niemand', quiet: true });
    expect(tiles[3]).toMatchObject({ value: 'Niemand', quiet: true });
    expect(tiles[2]?.target).toBeUndefined();
    expect(tiles[3]?.target).toBeUndefined();
  });
});

describe('freeSummary', () => {
  it('says since when someone is free, in the words of the Inzet board', () => {
    expect(freeSummary(NOOR)).toBe('Vrij, laatste inzet tot 30 nov 2025');
    expect(freeSummary({ ...NOOR, last_inzet_end: null })).toBe('Vrij, nog geen inzet gehad');
    expect(freeSummary(MILA)).toBe('');
    expect(freeSummary(ANNA)).toBe('');
    expect(freeSummary(ANNA, true)).toBe('Nu 20%, 80% vrij');
  });
});

function Address() {
  const location = useLocation();
  return <output data-testid="address">{location.pathname + location.search}</output>;
}

function renderBlock(occupancy: Occupancy = OCCUPANCY, search = '?jaar=2026') {
  return renderApp(
    <Routes>
      <Route
        path="/rapportage/bezetting"
        element={
          <>
            <OccupancyBlock occupancy={occupancy} year={2026} />
            <Address />
          </>
        }
      />
    </Routes>,
    { path: `/rapportage/bezetting${search}` },
  );
}

describe('OccupancyBlock', () => {
  const rowIds = (container: HTMLElement) =>
    [...container.querySelectorAll('tbody tr')].map((row) => row.getAttribute('data-person'));
  const tile = (key: string) => screen.getByTestId(`occupancy-tile-${key}`);
  const address = () => screen.getByTestId('address').textContent;

  it('leads with the figures and opens on the people with inzet', () => {
    const { container } = renderBlock();
    const figures = screen.getByRole('list', { name: 'Bezetting in het kort' });
    expect(tile('over')).toHaveTextContent('Boven 100%1 persoon');
    expect(tile('over')).toHaveTextContent('Te veel ingepland');
    const table = screen.getByRole('grid');
    expect(figures.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Problems first; the person without inzet is no row of empty cells.
    expect(rowIds(container)).toEqual(['p1', 'p3', 'p2']);
    expect(screen.getByTestId('occupancy')).toHaveTextContent(
      'Alleen de personen van wie je de inzet mag zien',
    );
  });

  it('makes each figure a link to exactly the people it counts', () => {
    const { container } = renderBlock();
    expect(tile('idle')).toHaveAttribute('href', '/rapportage/bezetting?jaar=2026&toon=zonder-inzet');
    expect(tile('over')).toHaveAttribute(
      'href',
      '/rapportage/bezetting?jaar=2026&toon=boven-100&maand=2026-09',
    );
    expect(tile('free')).toHaveAttribute(
      'href',
      '/rapportage/bezetting?jaar=2026&toon=vrij&volgorde=ruimte',
    );
    expect(tile('average')).toHaveAttribute('href', '/rapportage/bezetting?jaar=2026&toon=iedereen');

    fireEvent.click(tile('idle'));
    expect(address()).toBe('/rapportage/bezetting?jaar=2026&toon=zonder-inzet');
    // The one person the tile counted, as a row, with since when she is free.
    expect(rowIds(container)).toEqual(['p4']);
    expect(tile('idle')).toHaveAttribute('aria-current', 'true');
    const row = container.querySelector('tr[data-person="p4"] th')!;
    expect(row).toHaveTextContent('Vrij, laatste inzet tot 30 nov 2025');
    expect(row.querySelector('a')).toHaveAttribute('href', '/inzet?persoon=p4');
  });

  it('offers the way back to everyone while a figure filters the table', () => {
    const { container } = renderBlock(OCCUPANCY, '?jaar=2026&toon=zonder-inzet');
    expect(rowIds(container)).toEqual(['p4']);
    const everyone = container.querySelector('nldd-toolbar nldd-button[text="Toon iedereen"]')!;
    fireEvent(everyone, new MouseEvent('click'));
    expect(address()).toBe('/rapportage/bezetting?jaar=2026&toon=iedereen');
    expect(rowIds(container)).toHaveLength(4);
    expect(container.querySelector('nldd-toolbar nldd-button[text="Toon iedereen"]')).toBeNull();
  });

  it('opens the overbooked person on the month in question', () => {
    const { container } = renderBlock();
    fireEvent.click(tile('over'));
    expect(rowIds(container)).toEqual(['p1']);
    const cellInSeptember = cellOf(container, 'p1', '2026-09');
    expect(cellInSeptember).toHaveAttribute('aria-selected', 'true');
    expect(cellInSeptember).toHaveFocus();
    expect(screen.getByTestId('occupancy-detail')).toHaveTextContent('Mila Medewerker, september 2026');
  });

  it('sorts on room this month when the free figure is opened', () => {
    const { container } = renderBlock();
    fireEvent.click(tile('free'));
    // Most room first: Noor is fully free, then Anna (80), then Cas (50).
    expect(rowIds(container)).toEqual(['p4', 'p3', 'p2']);
    expect(container.querySelector('tr[data-person="p3"] th')).toHaveTextContent('Nu 20%, 80% vrij');
  });

  it('reads the view from the address, so it can be linked to', () => {
    const { container } = renderBlock(OCCUPANCY, '?jaar=2026&toon=iedereen&volgorde=naam');
    expect(rowIds(container)).toEqual(['p3', 'p2', 'p1', 'p4']);
    const selects = [...container.querySelectorAll<HTMLSelectElement>('nldd-toolbar select')];
    expect(selects.map((select) => select.value)).toEqual(['iedereen', 'name']);
  });

  it('says it once when both groups without inzet are the same people', () => {
    const { container } = renderBlock();
    const options = [...container.querySelectorAll('nldd-toolbar select')][0]!.querySelectorAll('option');
    const labels = [...options].map((option) => option.textContent);
    expect(labels).toEqual([
      'Met inzet in 2026 (3)',
      'Zonder inzet de komende 3 maanden (1)',
      'Boven 100% (1)',
      'Met ruimte in oktober 2026 (3)',
      'Iedereen (4)',
    ]);
  });

  it('gives each group its own control when they differ', () => {
    // Stef had inzet in March and has none ahead: counted by the figure, but
    // not without inzet in the whole year.
    const { container } = renderBlock({ ...OCCUPANCY, persons: [MILA, CAS, ANNA, NOOR, STEF] });
    const options = [...container.querySelectorAll('nldd-toolbar select')][0]!.querySelectorAll('option');
    const labels = [...options].map((option) => option.textContent);
    expect(labels).toContain('Zonder inzet de komende 3 maanden (2)');
    expect(labels).toContain('Zonder inzet in 2026 (1)');
    fireEvent.click(tile('idle'));
    expect(rowIds(container).sort()).toEqual(['p4', 'p5']);
  });

  it('keeps the line at the bottom for who is truly left out', () => {
    const { container } = renderBlock();
    const line = screen.getByTestId('occupancy-left-out');
    expect(line.querySelector('summary')).toHaveTextContent(
      '2 mensen staan er niet in: zonder inzetschaal en zonder inzet in 2026',
    );
    expect(line).not.toHaveAttribute('open');
    expect(line).toHaveTextContent('Bea Beheer, Lex Lezer');
    expect(container.querySelector('tbody')).not.toHaveTextContent('Bea Beheer');
    // No second line about people who are deployable: the figures lead to them.
    expect(screen.getByTestId('occupancy')).not.toHaveTextContent('Toon ze in de tabel');
  });

  it('has no left-out line when nobody is left out', () => {
    renderBlock({ ...OCCUPANCY, not_deployable: [] });
    expect(screen.queryByTestId('occupancy-left-out')).toBeNull();
  });

  it('opens a cell as one sentence, announced', () => {
    const { container } = renderBlock();
    expect(screen.queryByTestId('occupancy-detail')).toBeNull();
    const target = cellOf(container, 'p1', '2026-09');
    fireEvent.keyDown(target, { key: 'Enter' });

    const detail = screen.getByTestId('occupancy-detail');
    expect(detail.parentElement).toHaveAttribute('aria-live', 'polite');
    expect(detail).toHaveTextContent('Mila Medewerker, september 2026');
    // "130% ingepland: 100% vast op <opdracht>, 30% onder voorbehoud op ...".
    expect(detail.querySelector('p')).toHaveTextContent(
      /^130% ingepland: 100% vast op\s*, 30% onder voorbehoud \(mondeling akkoord\) op een opdracht die je niet mag inzien\.$/,
    );
    expect(detail.querySelector('nldd-link')).toHaveAttribute('href', '/opdrachten/a1');
    expect(detail.querySelector('nldd-link')).toHaveAttribute('text', 'Opdracht Alfa');
    expect(target).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(target, { key: 'Escape' });
    expect(screen.queryByTestId('occupancy-detail')).toBeNull();
  });

  it('states the full-time assumption quietly, not in the introduction', () => {
    renderBlock();
    const block = screen.getByTestId('occupancy');
    const quiet = [...block.querySelectorAll('nldd-text[color="secondary"]')].map(
      (text) => text.textContent,
    );
    expect(quiet.some((text) => text?.includes('Beschikbaar is 1 FTE per persoon per maand'))).toBe(
      true,
    );
    expect(quiet[0]).not.toContain('Beschikbaar is 1 FTE');
  });

  it('explains every state in a legend with words', () => {
    renderBlock();
    const legend = screen.getByRole('list', { name: 'Legenda van de bezetting' });
    for (const text of ['boven 100%', 'onder voorbehoud', 'vastgesteld', 'geen inzet', 'niet inzetbaar']) {
      expect(legend).toHaveTextContent(text);
    }
  });
});
