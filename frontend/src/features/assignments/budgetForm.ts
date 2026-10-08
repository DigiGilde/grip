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
  startDate: string;
  endDate: string;
  amount: string;
  year: string;
}

export function lineForm(line?: BudgetLine): LineForm {
  return {
    kind: line?.kind ?? 'personnel',
    description: line?.description ?? '',
    role: line?.role ?? '',
    personId: line?.intended_person_id ?? '',
    fte: decimalToInput(line?.fte),
    category: line?.rate_category ?? '',
    startDate: line?.start_date ?? '',
    endDate: line?.end_date ?? '',
    amount: centsToInput(line?.amount_cents),
    year: line?.year ? String(line.year) : String(new Date().getFullYear()),
  };
}

/** The request body, or a sentence saying what is wrong with the form. */
export function lineInput(
  form: LineForm,
  isNew: boolean,
  original?: BudgetLine,
): BudgetLineInput | string {
  const personnel = form.kind === 'personnel';
  if (personnel && !form.role.trim()) return 'Kies een rol.';
  // A personnel line is named by its role; the description only tells two apart.
  if (!personnel && !form.description.trim()) return 'Geef de regel een omschrijving.';
  const input: BudgetLineInput = { description: form.description.trim() };
  if (isNew) input.kind = form.kind;
  if (form.kind === 'personnel') {
    const fte = parseDecimal(form.fte);
    if (fte === null) return 'De omvang in FTE is een getal, bijvoorbeeld 0,8.';
    // With an intended person the server takes the category from them.
    if (!form.category && !form.personId) return 'Kies een schaal.';
    if (!form.startDate || !form.endDate) return 'Vul de begin- en einddatum in.';
    const personChanged = form.personId !== (original?.intended_person_id ?? '');
    return {
      ...input,
      role: form.role.trim() || null,
      fte,
      ...(form.category ? { rate_category: form.category } : {}),
      start_date: form.startDate,
      end_date: form.endDate,
      ...(personChanged ? { intended_person_id: form.personId || null } : {}),
    };
  }
  const cents = parseEuroToCents(form.amount);
  if (cents === null) return 'Het bedrag is geen geldig bedrag.';
  if (!/^\d{4}$/.test(form.year)) return 'Het jaar is een jaartal van vier cijfers.';
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
    ...(form.startDate ? { start_date: form.startDate } : {}),
    ...(form.endDate ? { end_date: form.endDate } : {}),
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
  return [parts.join(', '), ...(line.intended_notes ?? [])].join('. ');
}
