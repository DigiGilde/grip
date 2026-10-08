import type { ReactNode } from 'react';
import { formatPeriod } from '@/lib/format';
import { Button, DateInput } from './ui';

interface PeriodChoiceProps {
  /** What the period follows by default, as in "zelfde als de opdracht". */
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
  /** Shown when the parent has no period yet: a way to set it right here. */
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
        <nldd-text>
          {known
            ? `Periode: zelfde als ${parent} (${formatPeriod(parentStart, parentEnd)})`
            : `Periode: zelfde als ${parent}, die nog geen looptijd heeft`}
        </nldd-text>
        {!known && whenMissing}
        <nldd-container layout="row">
          <Button text="Afwijkende periode" onClick={() => onOwn(true)} />
        </nldd-container>
      </nldd-container>
    );
  }
  return (
    <nldd-container gap="8">
      <nldd-container layout="grid" column-count={2} gap="12">
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
        <Button text={`Zelfde als ${parent}`} onClick={() => onOwn(false)} />
      </nldd-container>
    </nldd-container>
  );
}
