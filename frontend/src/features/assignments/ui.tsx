/**
 * Small React bindings around the design-system elements these screens use.
 * They exist because nldd events are custom events on the element itself,
 * which a JSX `on*` prop never sees.
 */
import { MultiLineField, TextField } from '@/ui/fields';
import { useRef } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { dateFieldRange } from '@/ui/dateRange';

// Tests leave the nldd-* elements unregistered on purpose, so they read the
// light DOM this app is responsible for. Elements upgrade whenever their
// definition arrives, so loading it after the first render is fine.
if (import.meta.env.MODE !== 'test') void import('./register');

function eventValue(event: Event): string {
  const detail = (event as CustomEvent<{ value?: unknown }>).detail;
  if (detail && detail.value !== undefined && detail.value !== null) return String(detail.value);
  const target = event.target as { value?: unknown } | null;
  return target?.value === undefined || target.value === null ? '' : String(target.value);
}

export { Button, QuietButton } from '@/ui/Button';

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  optional?: boolean;
  hint?: string;
  required?: boolean;
  invalid?: boolean;
}

/** One line, or plain text of more lines with `multiline`. See `@/ui/fields`. */
export function TextInput({
  multiline,
  keyboard,
  ...field
}: FieldProps & { keyboard?: 'decimal' | 'numeric' | 'url'; multiline?: boolean }) {
  return multiline ? (
    <MultiLineField {...field} />
  ) : (
    <TextField {...field} {...(keyboard ? { keyboard } : {})} />
  );
}

export function DateInput({
  label,
  value,
  onChange,
  optional,
  hint,
  required,
  invalid,
}: FieldProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => onChange(eventValue(event)));
  useNlddEvent(ref, 'input', (event) => onChange(eventValue(event)));
  return (
    <nldd-form-field
      label={label}
      optional={orUndef(optional)}
      {...(hint ? { 'supporting-label': hint } : {})}
    >
      <nldd-date-field
        ref={ref}
        value={value}
        {...dateFieldRange()}
        required={orUndef(required)}
        invalid={orUndef(invalid)}
      />
    </nldd-form-field>
  );
}

export interface Option {
  value: string;
  label: string;
}

interface SelectProps extends Omit<FieldProps, 'invalid'> {
  options: readonly Option[];
  /** Text of the empty choice; omit to offer none. */
  placeholder?: string;
  disabled?: boolean;
}

export function SelectInput({
  label,
  value,
  onChange,
  options,
  placeholder,
  optional,
  hint,
  required,
  disabled,
}: SelectProps) {
  const ref = useRef<HTMLElement>(null);
  // The dropdown stops the native change event and sends its own, so a
  // handler on the slotted select would never fire.
  useNlddEvent(ref, 'change', (event) => onChange(eventValue(event)));
  return (
    <nldd-form-field
      label={label}
      optional={orUndef(optional)}
      {...(hint ? { 'supporting-label': hint } : {})}
    >
      <nldd-dropdown ref={ref} required={orUndef(required)} disabled={orUndef(disabled)}>
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          {placeholder !== undefined && <option value="">{placeholder}</option>}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </nldd-dropdown>
    </nldd-form-field>
  );
}

// One form sheet, one set of states and one filter select for all of grip:
// these come from the shared layout, and are passed on here for the screens
// that still import them from this file.
export {
  EmptyNotice,
  ErrorNotice,
  FilterSelect as InlineSelect,
  FormSheet,
  Loading,
  SectionHeading,
} from '@/ui/layout';
