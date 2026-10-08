import { describe, expect, it } from 'vitest';
import {
  assignLanes,
  barsInColumn,
  buildGroups,
  describeCell,
  mismatchText,
  personSummary,
  placePeriod,
  shiftMonth,
  totalState,
  totalText,
} from './model';
import { MONTHS, bar, board, cells } from './testing';

const plain = (text: string) => text.replace(/\u00a0|\u202f/g, ' ');

describe('placing a period on the months', () => {
  it('finds the first column and the span', () => {
    expect(placePeriod(MONTHS, '2026-04-15', '2026-05-31')).toEqual({
      column: 3,
      span: 2,
      clippedStart: false,
      clippedEnd: false,
    });
  });

  it('clips what starts before or ends after the months on screen', () => {
    expect(placePeriod(MONTHS, '2025-06-01', '2027-03-31')).toEqual({
      column: 0,
      span: 12,
      clippedStart: true,
      clippedEnd: true,
    });
  });

  it('leaves out what lies outside the months, and treats an open end as running on', () => {
    expect(placePeriod(MONTHS, '2027-01-01', '2027-03-31')).toBeNull();
    expect(placePeriod(MONTHS, '2026-11-01', null)).toMatchObject({ column: 10, span: 2 });
  });

  it('moves a month back and forth over the year boundary', () => {
    expect(shiftMonth('2026-01', -3)).toBe('2025-10');
    expect(shiftMonth('2026-11', 3)).toBe('2027-02');
  });
});

describe('lanes', () => {
  it('stacks bars that overlap and reuses a lane that is free again', () => {
    const bars = [
      { column: 0, span: 6, lane: 0 },
      { column: 3, span: 2, lane: 0 },
      { column: 7, span: 2, lane: 0 },
    ];
    expect(assignLanes(bars)).toBe(2);
    expect(bars.map((item) => item.lane)).toEqual([0, 1, 0]);
  });
});

describe('rows', () => {
  it('puts open roles above the people, each group with a quiet label', () => {
    const groups = buildGroups(board(), 'person', 'all');
    expect(groups.map((group) => group.title)).toEqual(['Open rollen', 'Mensen']);
    expect(groups[0]?.rows[0]?.label).toBe('Ontwerper');
    expect(plain(groups[0]?.rows[0]?.bars[0]?.label ?? '')).toBe('0,5 FTE open');
    expect(groups[0]?.rows[0]?.bars[0]).toMatchObject({ column: 4, span: 6, open: true });
  });

  it('gives a person a one-line summary and says overbooking louder', () => {
    const [first, second] = board().persons;
    expect(personSummary(first!)).toEqual({
      attention: 'Boven 100% in apr, mei',
      summary: 'Nu 110%, geen inzet vanaf jul',
    });
    expect(personSummary(second!)).toEqual({ attention: '', summary: 'Nu 100%' });
    expect(personSummary({ ...first!, idle_from: null }).summary).toBe('Nu 110%, ruimte vanaf jun');
    expect(personSummary({ ...first!, idle_from: '2026-04-01' }, '2026-04-01').summary).toBe(
      'Geen inzet gepland',
    );
  });

  it('stacks two inzetten of one person and marks the closed months', () => {
    const row = buildGroups(board(), 'person', 'all')[1]?.rows[0];
    expect(row?.lanes).toBe(2);
    expect(row?.bars.map((item) => [item.column, item.span, item.lane, item.closedSpan])).toEqual([
      [0, 6, 0, 2],
      [3, 2, 1, 0],
    ]);
    expect(row?.bars[1]).toMatchObject({ tentative: true, mismatch: true });
    expect(barsInColumn(row!, 3)).toHaveLength(2);
    expect(barsInColumn(row!, 6)).toHaveLength(0);
  });

  it('filters on room and on overbooking', () => {
    const names = (show: 'room' | 'over') =>
      buildGroups(board(), 'person', show).flatMap((group) => group.rows.map((row) => row.label));
    expect(names('over')).toEqual(['Voorbeeld Een']);
    expect(names('room')).toEqual(['Voorbeeld Een']);
  });

  it('groups by team, people without a line manager last', () => {
    const groups = buildGroups(board(), 'team', 'over');
    expect(groups.map((group) => group.title)).toEqual(['Team van Voorbeeld Leiding']);
    const all = buildGroups(board(), 'team', 'all').map((group) => group.title);
    expect(all).toEqual(['Open rollen', 'Team van Voorbeeld Leiding', 'Zonder leidinggevende']);
  });

  it('shows assignments with their roles and who fills them', () => {
    const groups = buildGroups(board(), 'assignment', 'all');
    expect(groups.map((group) => group.title)).toEqual(['Opdracht Alfa', 'Opdracht Epsilon']);
    const alfa = groups[0]!;
    expect(alfa.rows.map((row) => [row.label, row.summary])).toEqual([
      ['Ontwerper', 'Nog niemand'],
      ['Productmanager', '2 personen'],
    ]);
    expect(alfa.rows[0]?.attention).toContain('niet ingevuld');
    expect(plain(alfa.rows[1]?.bars[0]?.label ?? '')).toBe('80% Voorbeeld Een');
  });
});

describe('the total of a month', () => {
  const [past, , , over, , room, idle] = cells([80, 80, 80, 110, 110, 80, 0]);

  it('is quiet in the past and loud only when it needs attention', () => {
    expect(totalState(past!, MONTHS[0]!, '2026-04-01')).toBe('quiet');
    expect(totalState(over!, MONTHS[3]!, '2026-04-01')).toBe('over');
    expect(totalState(room!, MONTHS[5]!, '2026-04-01')).toBe('room');
    expect(totalState(idle!, MONTHS[6]!, '2026-04-01')).toBe('room');
    expect(totalState({ ...past!, available: false }, MONTHS[0]!, '2026-04-01')).toBe('unavailable');
    expect(totalState(null, MONTHS[0]!, '2026-04-01')).toBe('none');
  });

  it('says overbooking with a mark and room in words', () => {
    expect(totalText(over!, 'over')).toBe('! 110%');
    expect(totalText(room!, 'room')).toBe('vrij 20%');
    expect(totalText(past!, 'quiet')).toBe('80%');
  });
});

describe('a cell in words', () => {
  it('gives the total and every allocation, with how firm it is', () => {
    const row = buildGroups(board(), 'person', 'all')[1]!.rows[0]!;
    const text = plain(describeCell(row, 3, MONTHS[3]!, '2026-04-01'));
    expect(text).toContain('totaal 110%; boven 100%');
    expect(text).toContain('80% Opdracht Alfa, Productmanager');
    expect(text).toContain('vastgesteld t/m februari 2026');
    expect(text).toContain('30% Opdracht Epsilon');
    expect(text).toContain('onder voorbehoud');
    expect(text).toContain('andere categorie');
    expect(text).not.toContain('€');
  });

  it('names the categories only when the reader got them', () => {
    expect(mismatchText(bar({ category_mismatch: true }))).not.toMatch(/categorie [A-E]\b/);
    expect(
      mismatchText(bar({ category_mismatch: true, person_category: 'C', line_category: 'D' })),
    ).toContain('categorie C');
  });
});
