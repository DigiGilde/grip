import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderApp } from '@/test/utils';
import type { Occupancy, OccupancyCell, OccupancyMonth, PersonOccupancy } from '../api';
import { occupancyFigures } from './figures';
import { Heatmap } from './Heatmap';
import { describeCell, sortPersons } from './model';
import { OccupancyBlock } from './OccupancyBlock';
import { cellState, fillLevel } from './scale';

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
  { average_pct: '65', over_months: ['2026-09'] },
);
const CAS = person('p2', 'Cas Collega', { '2026-10': { pct: '50' } }, { average_pct: '25' });
const ANNA = person('p3', 'Anna Analist', { '2026-10': { pct: '20' } }, { average_pct: '10' });

const SUMMARY = {
  person_count: 3,
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
  idle_count: 2,
};

const OCCUPANCY: Occupancy = {
  scope: 'own',
  summary: SUMMARY,
  months: YEAR_MONTHS,
  persons: [MILA, CAS, ANNA],
  not_deployable: [
    { person_id: 'p8', person_name: 'Bea Beheer' },
    { person_id: 'p9', person_name: 'Lex Lezer' },
  ],
};

function renderHeatmap(persons = [MILA, CAS], currentMonth = '2026-10') {
  const selections: unknown[] = [];
  const utils = render(
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
    expect(mark('2026-09').querySelector('.grip-occ__value')).toHaveTextContent('! 130%');

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

describe('occupancyFigures', () => {
  it('says the answer before the table', () => {
    const figures = occupancyFigures(SUMMARY, 2026);
    expect(figures.map((figure) => [figure.label, figure.value])).toEqual([
      ['Gemiddelde bezetting 2026', '33,3%'],
      ['Vrij in oktober 2026', '1,3 FTE'],
      ['Boven 100%', '1 persoon'],
      ['Zonder inzet de komende 3 maanden', '2 mensen'],
    ]);
    expect(figures[1]?.detail).toBe('nov 2, dec 2,5, jan 3. Nu 0,3 FTE onder voorbehoud ingepland.');
    expect(figures[2]).toMatchObject({ attention: 'Te veel ingepland', detail: 'in sep' });
    expect(figures[3]).toMatchObject({ attention: 'Geen inzet gepland', detail: 'nov t/m jan' });
  });

  it('steps back when there is nothing to report', () => {
    const figures = occupancyFigures(
      { ...SUMMARY, over_count: 0, over_months: [], idle_count: 0 },
      2026,
    );
    expect(figures[2]).toMatchObject({ value: 'Niemand', quiet: true });
    expect(figures[3]).toMatchObject({ value: 'Niemand', quiet: true });
    expect(figures[2]?.attention).toBeUndefined();
  });
});

describe('OccupancyBlock', () => {
  const rowNames = (container: HTMLElement) =>
    [...container.querySelectorAll('tbody tr')].map((row) => row.getAttribute('data-person'));

  it('leads with the figures and sorts the problems to the top', () => {
    const { container } = renderApp(<OccupancyBlock occupancy={OCCUPANCY} year={2026} />);
    const figures = screen.getByLabelText('Bezetting in het kort');
    expect(figures).toHaveTextContent('Boven 100%1 persoon');
    expect(figures).toHaveTextContent('Te veel ingepland');
    // The figures come before the table in the document.
    const table = screen.getByRole('grid');
    expect(figures.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(rowNames(container)).toEqual(['p1', 'p3', 'p2']);
    expect(screen.getByTestId('occupancy')).toHaveTextContent(
      'Alleen de personen van wie je de inzet mag zien',
    );
  });

  it('switches to alphabetical order', () => {
    const { container } = renderApp(<OccupancyBlock occupancy={OCCUPANCY} year={2026} />);
    const control = container.querySelector('nldd-segmented-control')!;
    fireEvent(control, new CustomEvent('change', { detail: { value: 'name' } }));
    expect(rowNames(container)).toEqual(['p3', 'p2', 'p1']);
  });

  it('says how many people are left out and why, and can show them', () => {
    const { container } = renderApp(<OccupancyBlock occupancy={OCCUPANCY} year={2026} />);
    const line = screen.getByTestId('occupancy-left-out');
    expect(line).toHaveTextContent(
      '2 mensen staan er niet in: zij hebben in 2026 geen inzetschaal en geen inzet.',
    );
    expect(line).not.toHaveTextContent('Bea Beheer');
    // They are not rows of zeros.
    expect(container.querySelector('tbody')).not.toHaveTextContent('Bea Beheer');
    fireEvent(line.querySelector('nldd-button')!, new MouseEvent('click'));
    expect(line).toHaveTextContent('Bea Beheer, Lex Lezer');
  });

  it('keeps people without any inzet out of the table until asked', () => {
    const idle = person('p4', 'Noor Nieuw', {}, { average_pct: '0' });
    const { container } = renderApp(
      <OccupancyBlock occupancy={{ ...OCCUPANCY, persons: [idle, MILA, CAS] }} year={2026} />,
    );
    expect(rowNames(container)).toEqual(['p1', 'p2']);
    const line = screen.getByTestId('occupancy-bench');
    expect(line).toHaveTextContent('1 persoon is inzetbaar maar heeft in 2026 geen inzet.');
    fireEvent(line.querySelector('nldd-button')!, new MouseEvent('click'));
    // Shown on request, below the people who do have inzet.
    expect(rowNames(container)).toEqual(['p1', 'p2', 'p4']);
  });

  it('has no left-out line when nobody is left out', () => {
    renderApp(<OccupancyBlock occupancy={{ ...OCCUPANCY, not_deployable: [] }} year={2026} />);
    expect(screen.queryByTestId('occupancy-left-out')).toBeNull();
  });

  it('opens a cell: what the percentage consists of, announced', () => {
    const { container } = renderApp(<OccupancyBlock occupancy={OCCUPANCY} year={2026} />);
    expect(screen.queryByTestId('occupancy-detail')).toBeNull();
    const target = cellOf(container, 'p1', '2026-09');
    fireEvent.keyDown(target, { key: 'Enter' });

    const detail = screen.getByTestId('occupancy-detail');
    expect(detail.parentElement).toHaveAttribute('aria-live', 'polite');
    expect(detail).toHaveTextContent('Mila Medewerker, september 2026');
    expect(detail).toHaveTextContent('130%, boven 100%, waarvan 30% onder voorbehoud, gepland');
    expect(detail.querySelector('nldd-link')).toHaveAttribute('href', '/opdrachten/a1');
    expect(detail).toHaveTextContent('100%, gepland');
    // A part on an assignment the reader may not see comes without a name.
    expect(detail).toHaveTextContent(
      'Een opdracht die je niet mag inzien: 30%, onder voorbehoud, mondeling akkoord, gepland',
    );
    expect(target).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(target, { key: 'Escape' });
    expect(screen.queryByTestId('occupancy-detail')).toBeNull();
  });

  it('explains every state in a legend with words', () => {
    renderApp(<OccupancyBlock occupancy={OCCUPANCY} year={2026} />);
    const legend = screen.getByRole('list', { name: 'Legenda van de bezetting' });
    for (const text of ['boven 100%', 'onder voorbehoud', 'vastgesteld', 'geen inzet', 'niet inzetbaar']) {
      expect(legend).toHaveTextContent(text);
    }
  });
});
