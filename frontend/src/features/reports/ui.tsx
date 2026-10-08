import type { ReactNode } from 'react';
import { SectionHeading } from '@/features/assignments/ui';
import { formatEuro } from '@/lib/format';

// Tests leave the nldd-* elements unregistered on purpose, so they read the
// light DOM this app is responsible for.
if (import.meta.env.MODE !== 'test') void import('./register');

/** A block of a report: a heading, a line that says what it covers, and its content. */
export function ReportBlock({
  title,
  note,
  children,
  testId,
}: {
  title: string;
  note?: string;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <section data-testid={testId} aria-label={title}>
      <nldd-container gap="8">
        <SectionHeading text={title} />
        {note && (
          <nldd-text size="sm" color="secondary">
            {note}
          </nldd-text>
        )}
        {children}
      </nldd-container>
    </section>
  );
}

/** An amount in a table, right aligned. Empty when the API sent none. */
export function MoneyCell({
  cents,
  bold,
  note,
  critical,
}: {
  cents: number | null | undefined;
  bold?: boolean;
  note?: string;
  critical?: boolean;
}) {
  const text = formatEuro(cents);
  return (
    <nldd-text-cell
      text={bold && text ? `**${text}**` : text}
      horizontal-alignment="right"
      {...(note ? { 'supporting-text': note } : {})}
      {...(critical ? { color: 'critical' } : {})}
    />
  );
}

export function NumberCell({ text, note }: { text: string; note?: string }) {
  return (
    <nldd-text-cell
      text={text}
      horizontal-alignment="right"
      {...(note ? { 'supporting-text': note } : {})}
    />
  );
}
