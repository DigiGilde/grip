/**
 * Small React bindings around the design-system elements these screens use.
 * They exist because nldd events are custom events on the element itself,
 * which a JSX `on*` prop never sees.
 */
import { useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { orUndef, useNlddEvent } from '@/components/nldd/events';

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

interface ButtonProps {
  text: string;
  onClick?: () => void;
  appearance?: 'primary' | 'secondary' | 'destructive' | 'neutral-transparent';
  size?: 'xs' | 'sm' | 'md';
  type?: 'button' | 'submit';
  loading?: boolean;
  disabled?: boolean;
  accessibleLabel?: string;
  slot?: string;
}

export function Button({
  text,
  onClick,
  appearance = 'secondary',
  size,
  type,
  loading,
  disabled,
  accessibleLabel,
  slot,
}: ButtonProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick ? () => onClick() : undefined);
  return (
    <nldd-button
      ref={ref}
      text={text}
      appearance={appearance}
      {...(size ? { size } : {})}
      {...(type ? { type } : {})}
      {...(slot ? { slot } : {})}
      {...(accessibleLabel ? { 'accessible-label': accessibleLabel } : {})}
      loading={orUndef(loading)}
      disabled={orUndef(disabled)}
    />
  );
}

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  optional?: boolean;
  hint?: string;
  required?: boolean;
  invalid?: boolean;
}

export function TextInput({
  label,
  value,
  onChange,
  optional,
  hint,
  required,
  invalid,
  keyboard,
  multiline,
}: FieldProps & { keyboard?: 'decimal' | 'numeric' | 'url'; multiline?: boolean }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', (event) => onChange(eventValue(event)));
  return (
    <nldd-form-field
      label={label}
      optional={orUndef(optional)}
      {...(hint ? { 'supporting-label': hint } : {})}
    >
      {multiline ? (
        <nldd-multi-line-text-field ref={ref} value={value} invalid={orUndef(invalid)} />
      ) : (
        <nldd-text-field
          ref={ref}
          value={value}
          required={orUndef(required)}
          invalid={orUndef(invalid)}
          {...(keyboard ? { keyboard } : {})}
        />
      )}
    </nldd-form-field>
  );
}

export function DateInput({ label, value, onChange, optional, hint, required, invalid }: FieldProps) {
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
    <nldd-dropdown ref={ref} size="sm" accessible-label={label} {...(width ? { width } : {})}>
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
const NO_NATIVE_VALIDATION: object = { novalidate: '' };

interface FormSheetProps {
  open: boolean;
  /** Says what the sheet is about, e.g. "Opdracht Alfa bewerken". */
  title: string;
  submitText: string;
  onSubmit: () => void;
  onClose: () => void;
  busy?: boolean;
  error?: string | null;
  children: ReactNode;
}

/**
 * A form in a sheet, following the design system's pattern: the way out in
 * the title bar, the primary action under the last field. The sheet stays in
 * the document while closed, so its animation runs and focus returns to the
 * button that opened it.
 */
export function FormSheet({
  open,
  title,
  submitText,
  onSubmit,
  onClose,
  busy,
  error,
  children,
}: FormSheetProps) {
  const sheetRef = useRef<HTMLElement>(null);
  const barRef = useRef<HTMLElement>(null);
  const formRef = useRef<HTMLElement>(null);
  const titleId = useId();
  useNlddEvent(sheetRef, 'close', onClose);
  useNlddEvent(barRef, 'dismiss', onClose);
  useNlddEvent(formRef, 'submit', (event) => {
    event.preventDefault();
    if (!busy) onSubmit();
  });

  return createPortal(
    <nldd-sheet ref={sheetRef} open={orUndef(open)} placement="right" width="480px">
      <nldd-page>
        <nldd-top-title-bar
          ref={barRef}
          slot="header"
          text={title}
          dismiss-text="Annuleer"
          collapse-anchor={titleId}
        />
        <nldd-simple-section>
          <nldd-title id={titleId} slot="header" size={2} text={title} heading-level={1} />
          {error && <nldd-banner variant="critical" size="sm" text={error} />}
          <nldd-form ref={formRef} {...NO_NATIVE_VALIDATION}>
            {/* nldd-form moves its direct children into its own form element.
                React then loses track of siblings it wants to insert before, and
                a field that appears conditionally crashes the page. One stable
                wrapper that React owns keeps the fields together. */}
            <div className="form-fields">{children}</div>
            <nldd-form-actions>
              <nldd-button-group>
                <Button text={submitText} appearance="primary" type="submit" loading={busy} />
              </nldd-button-group>
            </nldd-form-actions>
          </nldd-form>
        </nldd-simple-section>
      </nldd-page>
    </nldd-sheet>,
    document.body,
  );
}

/** What a screen shows while loading, on an error, or when there is nothing. */
export function Loading({ text = 'Bezig met laden' }: { text?: string }) {
  return <nldd-inline-dialog variant="loading" text={text} />;
}

export function ErrorNotice({ message }: { message: string }) {
  return <nldd-banner variant="critical" size="sm" text={message} />;
}

export function EmptyNotice({ text, supportingText }: { text: string; supportingText?: string }) {
  return (
    <nldd-inline-dialog
      text={text}
      {...(supportingText ? { 'supporting-text': supportingText } : {})}
    />
  );
}

/** A section heading below the page's h1. */
export function SectionHeading({ text, level = 2 }: { text: string; level?: 2 | 3 }) {
  return <nldd-title size={level === 2 ? 3 : 4} text={text} heading-level={level} />;
}
