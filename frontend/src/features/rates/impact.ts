import { formatDate, formatEuro, formatMonth } from '@/lib/format';
import type { ActivationPreview, PriceImpact } from './api';
import { validityText } from './validity';

/** "€ 1.250 hoger", "€ 300 lager". The amount comes from the server; only its sign is read here. */
function higherLower(cents: number): string {
  return `${formatEuro(cents < 0 ? -cents : cents)} ${cents < 0 ? 'lager' : 'hoger'}`;
}

function count(n: number, one: string, many: string): string {
  return n === 1 ? `1 ${one}` : `${n} ${many}`;
}

const STATE_WORDS: Record<string, string> = {
  delivered: 'aangeleverd',
  invoiced: 'gefactureerd',
};

/**
 * What a change of price does, in plain sentences: what gets another amount
 * from the date, what happens to closed months, and the naverrekening that
 * arises for months that were already delivered.
 */
export function impactSentences(impact: PriceImpact, from: string): string[] {
  const sentences: string[] = [];
  const date = formatDate(from);

  if (impact.budget_lines_changed === 0 && impact.allocations_changed === 0) {
    sentences.push(
      `Vanaf ${date} verandert er geen bedrag: niets is in die periode begroot of ingezet.`,
    );
  } else {
    if (impact.budget_lines_changed > 0) {
      sentences.push(
        `${count(impact.budget_lines_changed, 'begrotingsregel krijgt', 'begrotingsregels krijgen')} vanaf ${date} een ander begroot bedrag, samen ${higherLower(impact.budget_difference_cents)}.`,
      );
    }
    const signed = impact.signed_assignments_changed ?? 0;
    if (signed > 0) {
      sentences.push(
        `Daaronder ${count(signed, 'opdracht', 'opdrachten')} met een getekende offerte: de begroting komt daar samen ${higherLower(impact.signed_difference_cents ?? 0)} uit dan wat is getekend.`,
      );
    }
    if (impact.allocations_changed > 0) {
      sentences.push(
        `${count(impact.allocations_changed, 'inzet krijgt', 'inzetten krijgen')} vanaf ${date} een ander bedrag. In de maanden die nog open zijn is dat samen ${higherLower(impact.open_difference_cents)}.`,
      );
    }
  }

  if (impact.closed_difference_cents !== 0) {
    sentences.push(
      `Afgesloten maanden die nog niet zijn aangeleverd, worden samen ${higherLower(impact.closed_difference_cents)}; het vastgestelde percentage blijft.`,
    );
  } else if (impact.correction_cents === 0) {
    sentences.push('Afgesloten maanden veranderen niet.');
  }

  if (impact.correction_cents !== 0) {
    sentences.push(
      `Voor maanden die al zijn aangeleverd ontstaat een naverrekening van samen ${higherLower(impact.correction_cents)}. De aanlevering zelf blijft zoals ze was.`,
    );
    for (const assignment of impact.assignments) {
      const months = assignment.months.filter((m) => m.state in STATE_WORDS);
      if (months.length === 0) continue;
      const parts = months.map((m) => {
        const invoice = m.invoice_number ? `, factuur ${m.invoice_number}` : '';
        return `${formatMonth(m.month)} (${STATE_WORDS[m.state]}${invoice}) ${higherLower(m.difference_cents)}`;
      });
      sentences.push(`${assignment.assignment_name}: ${parts.join('; ')}.`);
    }
  }

  if (impact.unpriced_months > 0) {
    sentences.push(
      `${count(impact.unpriced_months, 'maand is', 'maanden zijn')} daarna niet meer te prijzen, omdat er geen tarievenkaart voor geldt.`,
    );
  }
  return sentences;
}

/** What activating a draft card does. */
export function activationSentences(preview: ActivationPreview): string[] {
  const sentences: string[] = [];
  const { card, shortened, impact } = preview;
  if (shortened) {
    sentences.push(
      `De tarievenkaart '${shortened.name}' eindigt op ${formatDate(shortened.new_valid_to)}.`,
    );
  }
  sentences.push(`'${card.name}' is daarna ${validityText(card.valid_from, card.valid_to)}.`);
  if (impact.reaches_into_the_past) {
    sentences.push('De begindatum ligt in het verleden.');
  }
  for (const gap of preview.gaps ?? []) {
    const period = `${formatDate(gap.start_date)} t/m ${formatDate(gap.end_date)}`;
    const drafts =
      gap.drafts.length === 0
        ? 'Er is voor die periode geen tarievenkaart.'
        : gap.drafts.length === 1
          ? `Het concept '${gap.drafts[0]}' is nog niet vastgesteld.`
          : `De concepten ${gap.drafts.map((name) => `'${name}'`).join(' en ')} zijn nog niet vastgesteld.`;
    sentences.push(
      `Van ${period} geldt dan geen vastgestelde tarievenkaart: inzet in die periode krijgt geen bedrag. ${drafts}`,
    );
  }
  return [...sentences, ...impactSentences(impact, card.valid_from)];
}
