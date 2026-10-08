/**
 * Bindings for the few design-system elements the quote, signing and monthly
 * close screens use that the assignment screens do not: a checkbox field, a
 * file field and a link. The rest comes from the assignment screens' helpers.
 */
import { useRef, useState } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import './register';

interface CheckboxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  required?: boolean;
  invalid?: boolean;
}

export function CheckboxInput({ label, checked, onChange, required, invalid }: CheckboxProps) {
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
      required={orUndef(required)}
      invalid={orUndef(invalid)}
    />
  );
}

interface FileInputProps {
  label: string;
  hint?: string;
  accept: string;
  onChange: (file: File | null) => void;
  invalid?: boolean;
}

export function FileInput({ label, hint, accept, onChange, invalid }: FileInputProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => {
    const detail = (event as CustomEvent<{ files?: File[] }>).detail;
    onChange(detail?.files?.[0] ?? null);
  });
  return (
    <nldd-form-field label={label} {...(hint ? { 'supporting-label': hint } : {})}>
      <nldd-file-field ref={ref} accept={accept} required invalid={orUndef(invalid)} />
    </nldd-form-field>
  );
}

/** A link that leaves the screen: the quote document, a download. */
export function DocumentLink({
  href,
  text,
  newTab,
}: {
  href: string;
  text: string;
  newTab?: boolean;
}) {
  return <nldd-link href={href} text={text} size="md" {...(newTab ? { target: '_blank' } : {})} />;
}

interface CopyButtonProps {
  /** What the button says, e.g. "Kopieer tekenlink". */
  text: string;
  /** What lands on the clipboard. */
  value: string;
  appearance?: 'primary' | 'secondary' | 'neutral-transparent';
  size?: 'sm' | 'md';
}

/** Puts a text on the clipboard and says so on the button for a moment. */
export function CopyButton({ text, value, appearance = 'secondary', size }: CopyButtonProps) {
  const ref = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);
  useNlddEvent(ref, 'click', () => {
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  });
  return (
    <nldd-button
      ref={ref}
      appearance={appearance}
      text={copied ? 'Gekopieerd' : text}
      {...(size ? { size } : {})}
      aria-live="polite"
    />
  );
}

/** One choice in a "meer acties" menu. */
export function MenuAction({ text, onSelect }: { text: string; onSelect: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', onSelect);
  return <nldd-menu-item ref={ref} text={text} />;
}
