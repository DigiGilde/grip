/** The form behind a budget line: what a person types, and the request it becomes. */
import type { BudgetLine, BudgetLineInput } from './api';
import { centsToInput, decimalToInput, parseDecimal, parseEuroToCents } from './money';

export interface LineForm {
  kind: string;
  description: string;
  role: string;
  /** The intended person; empty for none. */
  personId: string;
  fte: string;
  category: string;
  /** True when the line has its own period; otherwise it follows the assignment. */
  ownPeriod: boolean;
  startDate: string;
  endDate: string;
  amount: string;
  year: string;
}

/** The period a line follows unless it has its own. */
export interface ParentPeriod {
  start: string | null | undefined;
  end: string | null | undefined;
}

/** The dates a line runs over: its own, or those of the assignment. */
export function effectivePeriod(form: LineForm, parent?: ParentPeriod) {
  return form.ownPeriod
    ? { start: form.startDate, end: form.endDate }
    : { start: parent?.start ?? '', end: parent?.end ?? '' };
}

/** A saved line deviates when its dates are not those of the assignment. */
export function hasOwnPeriod(line: BudgetLine | undefined, parent?: ParentPeriod): boolean {
  if (line?.period_source) return line.period_source === 'own';
  if (!line?.start_date && !line?.end_date) return false;
  return line.start_date !== parent?.start || line.end_date !== parent?.end;
}

/**
 * The year a new fixed amount most likely belongs to: this year when the
 * assignment runs in it, otherwise the first year of the assignment.
 */
export function proposedYear(parent?: ParentPeriod, today = new Date()): string {
  const now = today.getFullYear();
  const first = parent?.start ? Number(parent.start.slice(0, 4)) : null;
  const last = parent?.end ? Number(parent.end.slice(0, 4)) : null;
  if (first === null) return String(now);
  if (now >= first && (last === null || now <= last)) return String(now);
  return String(first);
}

export function lineForm(line?: BudgetLine, parent?: ParentPeriod): LineForm {
  return {
    ownPeriod: line?.kind !== 'fixed' && hasOwnPeriod(line, parent),
    kind: line?.kind ?? 'personnel',
    // The form edits the detail; the shown name is the role plus the detail.
    description: line?.detail ?? (line?.role ? '' : (line?.description ?? '')),
    role: line?.role ?? '',
    personId: line?.intended_person_id ?? '',
    fte: decimalToInput(line?.fte),
    category: line?.rate_category ?? '',
    startDate: line?.start_date ?? '',
    endDate: line?.end_date ?? '',
    amount: centsToInput(line?.amount_cents),
    year: line?.year ? String(line.year) : proposedYear(parent),
  };
}

export type LineField = 'role' | 'description' | 'fte' | 'category' | 'period' | 'amount' | 'year';

/** The first thing wrong with the form: which field, and a sentence for under it. */
export function checkLine(form: LineForm): { field: LineField; message: string } | null {
  if (form.kind === 'personnel') {
    if (!form.role.trim()) return { field: 'role', message: 'Kies een rol.' };
    if (parseDecimal(form.fte) === null) {
      return { field: 'fte', message: 'De omvang in FTE is een getal, bijvoorbeeld 0,8.' };
    }
    if (form.ownPeriod && (!form.startDate || !form.endDate)) {
      return { field: 'period', message: 'Vul de begin- en einddatum in.' };
    }
    if (form.ownPeriod && form.endDate < form.startDate) {
      return { field: 'period', message: 'De einddatum ligt voor de begindatum.' };
    }
    // With an intended person the server takes the category from them.
    if (!form.category && !form.personId) return { field: 'category', message: 'Kies een schaal.' };
    return null;
  }
  // A personnel line is named by its role; a fixed amount needs a description.
  if (!form.description.trim()) {
    return { field: 'description', message: 'Geef de regel een omschrijving.' };
  }
  if (parseEuroToCents(form.amount) === null) {
    return { field: 'amount', message: 'Het bedrag is geen geldig bedrag.' };
  }
  if (!/^\d{4}$/.test(form.year)) {
    return { field: 'year', message: 'Het jaar is een jaartal van vier cijfers.' };
  }
  return null;
}

/** The request body, or a sentence saying what is wrong with the form. */
export function lineInput(
  form: LineForm,
  isNew: boolean,
  original?: BudgetLine,
): BudgetLineInput | string {
  const problem = checkLine(form);
  if (problem) return problem.message;
  const input: BudgetLineInput = { description: form.description.trim() };
  if (isNew) input.kind = form.kind;
  if (form.kind === 'personnel') {
    const fte = parseDecimal(form.fte);
    const personChanged = form.personId !== (original?.intended_person_id ?? '');
    return {
      ...input,
      role: form.role.trim() || null,
      fte,
      ...(form.category ? { rate_category: form.category } : {}),
      // A following line sends no dates: it moves with the assignment.
      ...(form.ownPeriod
        ? { period_source: 'own' as const, start_date: form.startDate, end_date: form.endDate }
        : { period_source: 'assignment' as const }),
      ...(personChanged ? { intended_person_id: form.personId || null } : {}),
    };
  }
  const cents = parseEuroToCents(form.amount);
  if (cents === null) return 'Het bedrag is geen geldig bedrag.';
  return { ...input, amount_cents: cents, year: Number(form.year) };
}

/** The values to price, as far as the form is filled in. */
export function previewInput(form: LineForm): BudgetLineInput {
  if (form.kind === 'fixed') {
    const cents = parseEuroToCents(form.amount);
    return {
      kind: 'fixed',
      ...(cents !== null ? { amount_cents: cents } : {}),
      ...(/^\d{4}$/.test(form.year) ? { year: Number(form.year) } : {}),
    };
  }
  const fte = parseDecimal(form.fte);
  return {
    kind: 'personnel',
    ...(fte !== null && Number(fte) > 0 ? { fte } : {}),
    ...(form.category ? { rate_category: form.category } : {}),
    // A following line is priced by the server over the assignment's period.
    ...(form.ownPeriod
      ? {
          period_source: 'own' as const,
          ...(form.startDate ? { start_date: form.startDate } : {}),
          ...(form.endDate ? { end_date: form.endDate } : {}),
        }
      : { period_source: 'assignment' as const }),
  };
}

/** The intended person of a line, in the staffing sense; empty for a reader without it. */
export function intendedText(line: BudgetLine): string {
  if (!line.intended_person_name) return '';
  const parts = [`Beoogd: ${line.intended_person_name}`];
  if (line.intended_tentative) parts.push('onder voorbehoud');
  if (line.intended_in_step === false) {
    parts.push('de reservering loopt niet meer gelijk met de regel');
  }
  if (line.intended_category_differs) {
    parts.push('declareert in een andere schaal dan de regel aanneemt');
  }
  return parts.join(', ');
}
