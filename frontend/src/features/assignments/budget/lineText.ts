/** The words of a budget line, the same in the list to enter and in the state of the budget. */
import { formatFte, formatPeriod } from '@/lib/format';
import type { BudgetLine } from '../api';
import { hasOwnPeriod, yearOutsidePeriod, type ParentPeriod } from '../budgetForm';
import type { CategoryNamer } from '../rateText';

/** A personnel line is named by its role when it has no description of its own. */
export const lineName = (line: BudgetLine) => line.description || line.role || 'Begrotingsregel';

const lower = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

/** FTE and scale of a line, as far as the reader gets them, or that it is a fixed amount. */
export function lineSummary(line: BudgetLine, name: CategoryNamer, parent?: ParentPeriod): string {
  if (line.kind === 'fixed') {
    if (!line.year) return 'Vast bedrag';
    return yearOutsidePeriod(line, parent)
      ? `Vast bedrag, ${line.year}: buiten de looptijd`
      : `Vast bedrag, ${line.year}`;
  }
  const parts = [
    line.fte ? `${formatFte(line.fte)} FTE` : '',
    line.rate_category ? lower(name(line.rate_category, line.start_date)) : '',
    // Following the assignment is the normal case; only a deviation is said.
    !parent || hasOwnPeriod(line, parent)
      ? `afwijkende periode: ${formatPeriod(line.start_date, line.end_date)}`
      : '',
  ];
  const summary = parts.filter(Boolean).join(', ');
  return summary.charAt(0).toUpperCase() + summary.slice(1);
}
