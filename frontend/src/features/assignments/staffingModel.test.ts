import { describe, expect, it } from 'vitest';
import type { AssignmentStaffing, RoleStaffing } from './staffingApi';
import { legendOf, overbookedSignals, staffingRows, staffingSentence } from './staffingModel';

const MONTHS = ['2026-10-01', '2026-11-01', '2026-12-01'];
const role = (overrides: Partial<RoleStaffing> = {}): RoleStaffing => ({
  budget_line_id: 'l1',
  description: 'Adviseur',
  role: 'Adviseur',
  fte: '1.000',
  start_date: '2026-10-01',
  end_date: '2026-12-31',
  months: [],
  bars: [],
  gaps: [],
  fully_staffed: true,
  ...overrides,
});
const staffing = (
  roles: RoleStaffing[],
  overrides: Partial<AssignmentStaffing> = {},
): AssignmentStaffing => ({
  assignment_id: 'a1',
  months: MONTHS,
  current_month: '2026-10-01',
  tentative: false,
  roles,
  ...overrides,
});
const bar = {
  allocation_id: 'x1',
  person_id: 'p1',
  person_name: 'Voorbeeld Een',
  budget_line_id: 'l1',
  start_date: '2026-10-08',
  end_date: '2026-12-31',
  fte_pct: '100.0',
  closed_months: [],
  tentative: false,
  can_edit: true,
};

describe('the state of the staffing in one sentence', () => {
  it('says everything is filled', () => {
    expect(staffingSentence(staffing([role()]))).toBe('De rol is ingevuld.');
    expect(staffingSentence(staffing([role(), role({ budget_line_id: 'l2' })]))).toBe(
      'Alle rollen zijn ingevuld.',
    );
  });

  it('names what is open, how much and from when', () => {
    const open = role({
      budget_line_id: 'l2',
      description: 'Developer',
      fully_staffed: false,
      gaps: [{ start: '2027-01-01', end: '2027-03-01', open_fte: '0.50' }],
    });
    expect(staffingSentence(staffing([role(), open, role({ budget_line_id: 'l3' })]))).toBe(
      '1 van 3 rollen is nog open: Developer, 0,5 FTE vanaf januari 2027.',
    );
  });

  it('gives the double booking as who, when and how much', () => {
    const signals = overbookedSignals(
      staffing([role()], {
        overbooked: [
          { person_id: 'p1', person_name: 'Voorbeeld Een', month: '2026-10-01', pct: '140.0' },
        ],
      }),
    );
    expect(signals).toEqual([
      { key: 'p1', text: 'Voorbeeld Een zit in oktober 2026 op 140%', personId: 'p1' },
    ]);
    expect(overbookedSignals(staffing([role()]))).toEqual([]);
  });
});

describe('the picture', () => {
  it('has a legend of only the marks that occur', () => {
    const filled = staffingRows(staffing([role({ bars: [bar as never] })]));
    expect(legendOf(filled)).toEqual(['demand', 'filled']);
    const open = staffingRows(
      staffing([
        role({
          fully_staffed: false,
          gaps: [{ start: '2026-10-01', end: '2026-12-01', open_fte: '1.00' }],
        }),
      ]),
    );
    expect(legendOf(open)).toEqual(['demand', 'open']);
  });

  it('places a bar from its first to its last day', () => {
    const [group] = staffingRows(staffing([role({ bars: [bar as never] })]));
    const placed = group?.rows[0]?.bars.find((item) => item.key === 'x1');
    // 8 October: seven of 31 days are left free at the start.
    expect(placed?.startOffset).toBeCloseTo(7 / 31);
    expect(placed?.endOffset).toBe(0);
  });
});
