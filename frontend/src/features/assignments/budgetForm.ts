/** The form behind a budget line: what a person types, and the request it becomes. */
import type { BudgetLine, BudgetLineInput } from './api';
import { centsToInput, decimalToInput, parseDecimal, parseEuroToCents } from './money';

export interface LineForm {
  kind: string;
  description: string;
  role: string;
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
    fte: decimalToInput(line?.fte),
    category: line?.rate_category ?? '',
    startDate: line?.start_date ?? '',
    endDate: line?.end_date ?? '',
    amount: centsToInput(line?.amount_cents),
    year: line?.year ? String(line.year) : String(new Date().getFullYear()),
  };
}

/** The request body, or a sentence saying what is wrong with the form. */
export function lineInput(form: LineForm, isNew: boolean): BudgetLineInput | string {
  if (!form.description.trim()) return 'Geef de regel een omschrijving.';
  const input: BudgetLineInput = { description: form.description.trim() };
  if (isNew) input.kind = form.kind;
  if (form.kind === 'personnel') {
    const fte = parseDecimal(form.fte);
    if (fte === null) return 'De omvang in FTE is een getal, bijvoorbeeld 0,8.';
    if (!form.category) return 'Kies een tariefcategorie.';
    if (!form.startDate || !form.endDate) return 'Vul de begin- en einddatum in.';
    return {
      ...input,
      role: form.role.trim() || null,
      fte,
      rate_category: form.category,
      start_date: form.startDate,
      end_date: form.endDate,
    };
  }
  const cents = parseEuroToCents(form.amount);
  if (cents === null) return 'Het bedrag is geen geldig bedrag.';
  if (!/^\d{4}$/.test(form.year)) return 'Het jaar is een jaartal van vier cijfers.';
  return { ...input, amount_cents: cents, year: Number(form.year) };
}
