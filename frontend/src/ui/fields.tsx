/**
 * The text fields of grip, one per kind of text.
 *
 *   TextField       one line
 *   MultiLineField  plain text of more lines that stays plain: a reason, a
 *                   note, a remark, an instruction. Shown again as plain text
 *   TextEditor      (in ./TextEditor) text that is stored with marks and shown
 *                   formatted: a vacancy text, a section of a quote
 *
 * A field that is shown as plain text never gets the editor: its marks would
 * print as asterisks. See docs/ontwerp.md.
 */
import { useRef, type ReactNode } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';

if (import.meta.env.MODE !== 'test') void import('./text/register');

/** The value an nldd field reports with its input event. */
function eventValue(event: Event): string {
  const detail = (event as CustomEvent<{ value?: unknown }>).detail;
  if (detail && typeof detail.value === 'string') return detail.value;
  return (event.target as { value?: string } | null)?.value ?? '';
}

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** One line under the label; not an explanation of the interface. */
  hint?: string;
  optional?: boolean;
  required?: boolean;
  invalid?: boolean;
}

interface TextFieldProps extends FieldProps {
  type?: 'text' | 'email';
  keyboard?: 'decimal' | 'numeric' | 'url';
  autocomplete?: string;
  children?: ReactNode;
}

/** A labelled field of one line. */
export function TextField({
  label,
  value,
  onChange,
  hint,
  optional,
  required,
  invalid,
  type,
  keyboard,
  autocomplete,
  children,
}: TextFieldProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', (event) => onChange(eventValue(event)));
  return (
    <nldd-form-field
      label={label}
      optional={orUndef(optional)}
      {...(hint ? { 'supporting-label': hint } : {})}
    >
      <nldd-text-field
        ref={ref}
        value={value}
        {...(type ? { type } : {})}
        {...(keyboard ? { keyboard } : {})}
        {...(autocomplete ? { autocomplete } : {})}
        required={orUndef(required)}
        invalid={orUndef(invalid)}
      />
      {children}
    </nldd-form-field>
  );
}

interface MultiLineFieldProps extends FieldProps {
  /** How high the field opens; it grows with the text. Default 4. */
  rows?: number;
}

/** A labelled field for plain text of more than one line. */
export function MultiLineField({
  label,
  value,
  onChange,
  hint,
  optional,
  required,
  invalid,
  rows = 4,
}: MultiLineFieldProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', (event) => onChange(eventValue(event)));
  return (
    <nldd-form-field
      label={label}
      optional={orUndef(optional)}
      {...(hint ? { 'supporting-label': hint } : {})}
    >
      <nldd-multi-line-text-field
        ref={ref}
        value={value}
        rows={rows}
        required={orUndef(required)}
        invalid={orUndef(invalid)}
      />
    </nldd-form-field>
  );
}
