/**
 * One select on its own, at the same size step as the fields and buttons
 * around it. For a row of filters next to an action use `@/ui/ActionBar`.
 */
import { useRef } from 'react';
import { useNlddEvent } from '@/components/nldd/events';

if (import.meta.env.MODE !== 'test') void import('@nldd/design-system/dropdown');

function eventValue(event: Event): string {
  const detail = (event as CustomEvent<{ value?: unknown }>).detail;
  if (detail && detail.value !== undefined && detail.value !== null) return String(detail.value);
  const target = event.target as { value?: unknown } | null;
  return target?.value === undefined || target.value === null ? '' : String(target.value);
}

interface FilterSelectProps {
  /** Accessible name; the select has no visible label. */
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
  width?: string;
}

export function FilterSelect({ label, value, onChange, options, width }: FilterSelectProps) {
  const ref = useRef<HTMLElement>(null);
  // The dropdown stops the native change event of the slotted select and
  // sends its own, so a handler on the select alone never fires.
  useNlddEvent(ref, 'change', (event) => onChange(eventValue(event)));
  return (
    <nldd-dropdown ref={ref} accessible-label={label} {...(width ? { width } : {})}>
      <select value={value} aria-label={label} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </nldd-dropdown>
  );
}
