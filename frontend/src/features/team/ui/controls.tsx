import { Button as SharedButton, QuietButton } from '@/ui/Button';
import { TextField as SharedTextField } from '@/ui/fields';
import { useRef, type ReactNode } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import './nldd';
import { dateFieldRange } from '@/ui/dateRange';

function eventValue(event: Event): string {
  const detail = (event as CustomEvent<{ value?: unknown }>).detail;
  const fromDetail = detail && typeof detail === 'object' ? detail.value : undefined;
  const value = fromDetail ?? (event.target as { value?: unknown } | null)?.value;
  return value === undefined || value === null ? '' : String(value);
}

export type ButtonAppearance = 'primary' | 'secondary' | 'destructive' | 'neutral-transparent';

interface ButtonProps {
  text: string;
  onClick?: () => void;
  appearance?: ButtonAppearance;
  size?: 'xs' | 'sm' | 'md';
  type?: 'button' | 'submit';
  loading?: boolean;
  disabled?: boolean;
  slot?: string;
  accessibleLabel?: string;
}

/**
 * A button of the shared three ranks (`@/ui/Button`). The quiet appearance
 * exists here only for "Annuleer", the way out of a form.
 */
export function Button({ appearance = 'secondary', type = 'button', ...rest }: ButtonProps) {
  return appearance === 'neutral-transparent' ? (
    <QuietButton type={type} {...rest} />
  ) : (
    <SharedButton appearance={appearance} type={type} {...rest} />
  );
}

/** Keeps a filter field from stretching over the whole page. */
function Sized({ width, children }: { width?: string; children: ReactNode }) {
  return width ? <nldd-container width={width}>{children}</nldd-container> : <>{children}</>;
}

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  supportingLabel?: string;
  optional?: boolean;
  invalid?: boolean;
  /** A fixed width, for a field that filters a list rather than fills a form. */
  width?: string;
  children?: ReactNode;
}

interface TextFieldProps extends FieldProps {
  type?: 'text' | 'email';
  keyboard?: 'decimal' | 'numeric';
  required?: boolean;
  autocomplete?: string;
}

/** A labelled field of one line: the shared one (`@/ui/fields`). */
export function TextField({ supportingLabel, width: _width, ...field }: TextFieldProps) {
  return <SharedTextField {...field} {...(supportingLabel ? { hint: supportingLabel } : {})} />;
}

interface DateFieldProps extends FieldProps {
  required?: boolean;
}

/** A labelled date field; the value is an ISO date or empty. */
export function DateField({
  label,
  value,
  onChange,
  supportingLabel,
  optional,
  invalid,
  required,
  width,
}: DateFieldProps) {
  const ref = useRef<HTMLElement>(null);
  const handler = (event: Event) => onChange(eventValue(event));
  useNlddEvent(ref, 'change', handler);
  useNlddEvent(ref, 'input', handler);
  return (
    <Sized width={width}>
      <nldd-form-field
        label={label}
        {...(supportingLabel ? { 'supporting-label': supportingLabel } : {})}
        optional={orUndef(optional)}
      >
        <nldd-date-field
          ref={ref}
          value={value}
          {...dateFieldRange()}
          required={orUndef(required)}
          invalid={orUndef(invalid)}
        />
      </nldd-form-field>
    </Sized>
  );
}

export interface SelectOption {
  value: string;
  label: string;
  group?: string;
}

interface SelectFieldProps extends FieldProps {
  options: SelectOption[];
  /** Text of the empty choice; leave out when a choice is required. */
  emptyLabel?: string;
}

function groupOptions(options: SelectOption[]): Array<[string, SelectOption[]]> {
  const groups = new Map<string, SelectOption[]>();
  for (const option of options) {
    const key = option.group ?? '';
    groups.set(key, [...(groups.get(key) ?? []), option]);
  }
  return [...groups.entries()];
}

/** A labelled dropdown around a native select. */
export function SelectField({
  label,
  value,
  onChange,
  options,
  emptyLabel,
  supportingLabel,
  optional,
  invalid,
  width,
}: SelectFieldProps) {
  const ref = useRef<HTMLElement>(null);
  // The dropdown stops the native change event of the slotted select and
  // sends its own, so the handler on the select alone never fires.
  useNlddEvent(ref, 'change', (event) => onChange(eventValue(event)));
  return (
    <Sized width={width}>
      <nldd-form-field
        label={label}
        {...(supportingLabel ? { 'supporting-label': supportingLabel } : {})}
        optional={orUndef(optional)}
      >
        <nldd-dropdown ref={ref} invalid={orUndef(invalid)}>
          <select value={value} onChange={(event) => onChange(event.target.value)}>
            {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
            {groupOptions(options).map(([group, entries]) =>
              group ? (
                <optgroup key={group} label={group}>
                  {entries.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </optgroup>
              ) : (
                entries.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))
              ),
            )}
          </select>
        </nldd-dropdown>
      </nldd-form-field>
    </Sized>
  );
}

interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

function checkedOf(event: Event): boolean {
  const detail = (event as CustomEvent<{ checked?: boolean }>).detail;
  return Boolean(detail?.checked);
}

export function CheckboxField({ label, checked, onChange, disabled }: ToggleProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => onChange(checkedOf(event)));
  return (
    <nldd-checkbox-field
      ref={ref}
      label={label}
      checked={orUndef(checked)}
      disabled={orUndef(disabled)}
    />
  );
}

export function SwitchField({ label, checked, onChange, disabled }: ToggleProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => onChange(checkedOf(event)));
  return (
    <nldd-switch-field
      ref={ref}
      label={label}
      checked={orUndef(checked)}
      disabled={orUndef(disabled)}
    />
  );
}

interface SegmentsProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
}

/** A row of mutually exclusive choices, for switching between two views. */
export function Segments({ label, value, onChange, options }: SegmentsProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => {
    const next = eventValue(event);
    if (next) onChange(next);
  });
  return (
    <nldd-segmented-control ref={ref} value={value} accessible-label={label} width="fit-content">
      {options.map((option) => (
        <nldd-segmented-control-item key={option.value} value={option.value} text={option.label} />
      ))}
    </nldd-segmented-control>
  );
}

interface FileFieldProps {
  label: string;
  onChange: (files: File[]) => void;
  /** Comma-separated list of accepted types, as the native input takes it. */
  accept?: string;
  multiple?: boolean;
  supportingLabel?: string;
  optional?: boolean;
}

/** A labelled file picker. The chosen files arrive as a list; a clear gives an empty one. */
export function FileField({
  label,
  onChange,
  accept,
  multiple,
  supportingLabel,
  optional,
}: FileFieldProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => {
    const detail = (event as CustomEvent<{ files?: File[] }>).detail;
    onChange(Array.isArray(detail?.files) ? detail.files : []);
  });
  return (
    <nldd-form-field
      label={label}
      {...(supportingLabel ? { 'supporting-label': supportingLabel } : {})}
      optional={orUndef(optional)}
    >
      <nldd-file-field ref={ref} {...(accept ? { accept } : {})} multiple={orUndef(multiple)} />
    </nldd-form-field>
  );
}
