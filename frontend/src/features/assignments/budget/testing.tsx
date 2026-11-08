/** Test helpers for the part Begroting. Fictional data only. */
import { renderApp } from '@/test/utils';
import type { AssignmentDetail, Budget } from '../api';
import { BudgetPart } from '../parts/BudgetPart';
import type { AssignmentParts } from '../partsApi';
import { AssignmentFrameContext, AssignmentShellContext } from '../shell';

const BUDGET_ROW: AssignmentParts['parts'] = [{ key: 'budget', label: 'Begroting', notice: null }];

/** The part as the layout hands it down; `rows` are what the server gives this reader. */
export function renderBudgetPart(shell: AssignmentDetail, rows = BUDGET_ROW) {
  const parts: AssignmentParts = {
    assignment_id: shell.id,
    parts: rows,
    tasks_link: false,
    is_client: false,
    own_line: null,
  };
  return renderApp(
    <AssignmentShellContext.Provider value={shell}>
      <AssignmentFrameContext.Provider value={{ parts, course: null }}>
        <BudgetPart />
      </AssignmentFrameContext.Provider>
    </AssignmentShellContext.Provider>,
  );
}

export const BANDS = {
  rate_bands: [{ category: 'B', monthly_rate_cents: 1312500 }],
  scale_bands: [
    { scale: 10, category: 'B' },
    { scale: 11, category: 'B' },
    { scale: 14, category: 'D' },
    { scale: 15, category: 'D' },
  ],
};

export const CARDS = {
  may_manage: false,
  default_increase_pct: '0',
  items: [
    { status: 'active', valid_from: '2020-01-01', valid_to: null, name: 'Tarieven 2026', ...BANDS },
  ],
};

export const BUDGET: Budget = {
  assignment_id: 'a1',
  assignment_name: 'Opdracht Alfa 2026',
  can_edit: true,
  total_budgeted_cents: 17280000,
  subtotals_by_year: { '2026': 17280000 },
  quoted_amount_cents: null,
  pricing_error: null,
  lines: [
    {
      id: 'l1',
      assignment_id: 'a1',
      description: 'Productmanager',
      kind: 'personnel',
      position: 1,
      role: 'Productmanager',
      fte: '0.800',
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      rate_category: 'D',
      budgeted_cents: 17280000,
      budgeted_by_year: { '2026': 17280000 },
      pricing_error: null,
      intended_person_id: 'p1',
      intended_person_name: 'Voorbeeld Een',
      intended_tentative: true,
      intended_in_step: true,
      intended_notes: [],
    },
  ],
};
