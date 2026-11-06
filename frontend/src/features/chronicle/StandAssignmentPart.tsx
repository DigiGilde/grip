import { useAssignmentShell } from '@/features/assignments/shell';
import { formatEuro, formatPeriod } from '@/lib/format';
import { Facts, Section } from '@/ui/layout';
import type { Stand } from './api';

/** What the assignment said at this moment; each fact once on the screen. */
export function StandAssignmentPart({ stand }: { stand: Stand }) {
  const { assignment, moment, quotes } = stand;
  const nameNow = useAssignmentShell()?.name;
  const note = assignment.verbal_agreement_note;
  const amount = assignment.quoted_amount_cents;
  // The first quote sets this amount; the quote says it already while they agree.
  const amountTold = quotes.some(
    (quote) => quote.status !== 'superseded' && quote.total_cents === amount,
  );
  const facts = [
    {
      label: 'Naam',
      value: nameNow !== undefined && assignment.name !== nameNow ? assignment.name : '',
    },
    { label: 'Opdrachtgever', value: assignment.client_name ?? '' },
    { label: 'Periode', value: formatPeriod(assignment.start_date, assignment.end_date) },
    { label: 'Afgesproken bedrag', value: amountTold ? '' : formatEuro(amount) },
    // At its own moment the note is the reason under the sentence.
    { label: 'Mondeling akkoord', value: note && !moment.lines?.includes(note) ? note : '' },
    { label: 'Notities', value: assignment.notes ?? '' },
  ].filter((fact) => fact.value !== '');
  if (facts.length === 0) return null;
  return (
    <Section title="Opdracht" level={3}>
      <Facts label="Gegevens van de opdracht op dit moment" facts={facts} />
    </Section>
  );
}
