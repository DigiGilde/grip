/**
 * Small React bindings around the design-system elements the vacancy screens
 * use. Same shapes as the bindings of the assignment screens, so the two can
 * be merged into one shared module later.
 * They exist because nldd events are custom events on the element itself,
 * which a JSX `on*` prop never sees.
 */
import { MultiLineField, TextField } from '@/ui/fields';
import { iconAttribute } from '@/ui/icons';
import { useRef, type ReactNode } from 'react';
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
  /** Options with the same group are listed together under that heading. */
  group?: string;
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
          {options
            .filter((option) => !option.group)
            .map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          {[...new Set(options.map((option) => option.group).filter(Boolean))].map((group) => (
            <optgroup key={group} label={group}>
              {options
                .filter((option) => option.group === group)
                .map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </nldd-dropdown>
    </nldd-form-field>
  );
}

/** A select without a form field around it, for a filter above a table. */
export function InlineSelect({
  label,
  value,
  onChange,
  options,
  width,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly Option[];
  width?: string;
}) {
  const ref = useRef<HTMLElement>(null);
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

// The form's own messages are in English browser wording; each form checks
// its fields itself and says what is wrong in the banner above it. Spread as
// a plain attribute because the package types do not list it.

export { EmptyNotice, ErrorNotice, FormSheet, Loading } from '@/ui/layout';

/** A section heading below the page's h1. */
export function SectionHeading({ text, level = 2 }: { text: string; level?: 2 | 3 }) {
  return <nldd-title size={level === 2 ? 4 : 5} text={text} heading-level={level} />;
}

interface CheckboxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function CheckboxInput({ label, checked, onChange, disabled }: CheckboxProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => {
    const detail = (event as CustomEvent<{ checked?: boolean }>).detail;
    onChange(Boolean(detail?.checked));
  });
  return (
    <nldd-checkbox-field
      ref={ref}
      label={label}
      checked={orUndef(checked)}
      disabled={orUndef(disabled)}
    />
  );
}

interface FileProps {
  label: string;
  onChange: (file: File | null) => void;
  accept?: string;
  hint?: string;
}

export function FileInput({ label, onChange, accept, hint }: FileProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => {
    const detail = (event as CustomEvent<{ files?: File[] }>).detail;
    onChange(detail?.files?.[0] ?? null);
  });
  return (
    <nldd-form-field label={label} {...(hint ? { 'supporting-label': hint } : {})}>
      <nldd-file-field ref={ref} {...(accept ? { accept } : {})} />
    </nldd-form-field>
  );
}

/** A button that is a link: a download, or a page of the application. */
export function LinkButton({
  text,
  href,
  appearance = 'secondary',
  download,
}: {
  text: string;
  href: string;
  appearance?: 'primary' | 'secondary';
  download?: boolean;
}) {
  return (
    <nldd-button
      text={text}
      href={href}
      appearance={appearance}
      {...(download ? { download: '', ...iconAttribute('download') } : {})}
    />
  );
}

/** Plain text with blank lines as paragraph breaks, in the system's text style. */
export function Paragraphs({ text }: { text: string }) {
  const blocks = text
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
  return (
    <nldd-rich-text>
      {blocks.map((block, index) => (
        <p key={index} style={{ whiteSpace: 'pre-line' }}>
          {block}
        </p>
      ))}
    </nldd-rich-text>
  );
}

/** A secondary line of text: a note, an origin, an explanation. */
export function Note({ children }: { children: ReactNode }) {
  return (
    <nldd-text size="sm" color="secondary">
      {children}
    </nldd-text>
  );
}
