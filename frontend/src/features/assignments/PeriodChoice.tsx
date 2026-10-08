import type { ReactNode } from 'react';
import { formatPeriod } from '@/lib/format';
import { Button, DateInput } from './ui';

interface PeriodChoiceProps {
  /** What the period follows by default, as in "Loopt mee met de opdracht". */
  parent: string;
  parentStart?: string | null;
  parentEnd?: string | null;
  /** True when the period deviates and has its own two dates. */
  own: boolean;
  onOwn: (own: boolean) => void;
  startDate: string;
  endDate: string;
  onChange: (patch: { startDate?: string; endDate?: string }) => void;
  /** Said under the begin date, for example where a proposal comes from. */
  hint?: string;
  /** Shown when the parent has no period yet: the fields that ask for it. */
  whenMissing?: ReactNode;
}

/**
 * The period of something that normally follows its parent: one quiet line,
 * and two date fields only when it deviates.
 */
export function PeriodChoice({
  parent,
  parentStart,
  parentEnd,
  own,
  onOwn,
  startDate,
  endDate,
  onChange,
  hint,
  whenMissing,
}: PeriodChoiceProps) {
  const known = Boolean(parentStart && parentEnd);
  if (!own) {
    return (
      <nldd-container gap="8">
        {/* One calm line; the way out is a quiet link-like button under it. */}
        <nldd-text>
          {known
            ? `Loopt mee met ${parent}: ${formatPeriod(parentStart, parentEnd)}`
            : whenMissing
              ? `Loopt mee met ${parent}. Die heeft nog geen periode: vul haar hier in, zij wordt bij ${parent} bewaard.`
              : `Loopt mee met ${parent}; die heeft nog geen periode`}
        </nldd-text>
        {!known && whenMissing}
        <nldd-container layout="row">
          <Button text="Afwijkende periode" size="sm" onClick={() => onOwn(true)} />
        </nldd-container>
      </nldd-container>
    );
  }
  return (
    <nldd-container gap="8">
      <nldd-container layout="grid" column-count={2} gap="16">
        <DateInput
          label="Begindatum"
          {...(hint ? { hint } : {})}
          value={startDate}
          onChange={(value) => onChange({ startDate: value })}
          required
        />
        <DateInput
          label="Einddatum"
          value={endDate}
          onChange={(value) => onChange({ endDate: value })}
          required
        />
      </nldd-container>
      <nldd-container layout="row">
        <Button text={`Laat meelopen met ${parent}`} size="sm" onClick={() => onOwn(false)} />
      </nldd-container>
    </nldd-container>
  );
}
