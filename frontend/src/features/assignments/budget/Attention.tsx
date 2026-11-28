import { Section, type Signal as SignalItem, SignalList } from '@/ui/layout';
import type { AssignmentFinance } from '../financeApi';
import { signalText } from '../financeText';

const TONE = { critical: 'critical', warning: 'warning', neutral: 'info' } as const;

/** What asks for attention under the table: one list, the worst marked. */
export function Attention({ finance }: { finance: AssignmentFinance }) {
  // The difference with the signed quote stands under the table.
  const shown = finance.signals.filter((signal) => signal.kind !== 'budget_differs_from_agreed');
  if (shown.length === 0) return null;
  const signals: SignalItem[] = shown.map((signal, index) => {
    const { variant, text } = signalText(signal, finance.free_room_threshold_pct);
    return {
      key: `${signal.kind}-${signal.budget_line_id ?? index}`,
      text,
      tone: TONE[variant as keyof typeof TONE] ?? 'info',
    };
  });
  return (
    <Section title="Aandachtspunten">
      <SignalList label="Aandachtspunten" signals={signals} />
    </Section>
  );
}
