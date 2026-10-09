/** A fictional board for tests. */
import type { Board, BoardBar, BoardCell } from './api';

export const MONTHS = Array.from({ length: 12 }, (_, index) => {
  const month = index + 1;
  return `2026-${String(month).padStart(2, '0')}-01`;
});

export function cells(pcts: number[], extra: Partial<BoardCell>[] = []): BoardCell[] {
  return MONTHS.map((month, index) => ({
    month,
    available: true,
    pct: String(pcts[index] ?? 0),
    tentative_pct: '0',
    over: (pcts[index] ?? 0) > 100,
    established: false,
    ...(extra[index] ?? {}),
  }));
}

export function bar(overrides: Partial<BoardBar> = {}): BoardBar {
  return {
    allocation_id: 'x1',
    person_id: 'p1',
    person_name: 'Voorbeeld Een',
    assignment_id: 'a1',
    assignment_name: 'Opdracht Alfa',
    budget_line_id: 'l1',
    line_description: 'Productmanager',
    role: 'Productmanager',
    tentative: false,
    verbally_agreed: false,
    start_date: '2026-01-01',
    end_date: '2026-06-30',
    fte_pct: '80.00',
    closed_months: ['2026-01-01', '2026-02-01'],
    can_edit: true,
    category_mismatch: false,
    ...overrides,
  };
}

export function board(overrides: Partial<Board> = {}): Board {
  return {
    months: MONTHS,
    current_month: '2026-04-01',
    can_add: true,
    persons: [
      {
        person_id: 'p1',
        person_name: 'Voorbeeld Een',
        manager_id: 'm1',
        manager_name: 'Voorbeeld Leiding',
        cells: cells(
          [80, 80, 80, 110, 110, 80, 0, 0, 0, 0, 0, 0],
          [{ established: true }, { established: true }],
        ),
        now_pct: '110',
        room_from: '2026-06-01',
        idle_from: '2026-07-01',
        over_months: ['2026-04-01', '2026-05-01'],
        bars: [
          bar(),
          bar({
            allocation_id: 'x2',
            assignment_id: 'a2',
            assignment_name: 'Opdracht Epsilon',
            budget_line_id: 'l2',
            line_description: 'Developer',
            role: 'Developer',
            start_date: '2026-04-01',
            end_date: '2026-05-31',
            fte_pct: '30.00',
            tentative: true,
            closed_months: [],
            category_mismatch: true,
          }),
        ],
      },
      {
        person_id: 'p2',
        person_name: 'Voorbeeld Twee',
        manager_id: null,
        manager_name: null,
        cells: cells([100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100]),
        now_pct: '100',
        room_from: null,
        idle_from: null,
        over_months: [],
        bars: [
          bar({
            allocation_id: 'x3',
            person_id: 'p2',
            person_name: 'Voorbeeld Twee',
            start_date: '2025-06-01',
            end_date: '2027-03-31',
            fte_pct: '100.00',
            closed_months: [],
            can_edit: false,
          }),
        ],
      },
    ],
    open_roles: [
      {
        budget_line_id: 'l9',
        assignment_id: 'a1',
        assignment_name: 'Opdracht Alfa',
        description: 'Ontwerper',
        role: 'Ontwerper',
        fte: '1.000',
        unfilled_fte: '0.500',
        start_date: '2026-05-01',
        end_date: '2026-10-31',
        can_fill: true,
      },
    ],
    ...overrides,
  };
}
