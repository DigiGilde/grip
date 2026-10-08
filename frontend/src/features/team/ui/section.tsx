import type { ReactNode } from 'react';
import { Button, type ButtonAppearance } from './controls';
import './nldd';

export interface SectionAction {
  text: string;
  onClick: () => void;
  appearance?: ButtonAppearance;
  accessibleLabel?: string;
}

interface SectionProps {
  title: string;
  supportingText?: string;
  /** At most one action; it opens the fields, nothing is open by default. */
  action?: SectionAction | null;
  children?: ReactNode;
}

/**
 * A part of a page or sheet: a heading that says what is there, with at most
 * one action at the end of the heading line. A section shows what is; what
 * adds or changes opens from its action.
 */
export function Section({ title, supportingText, action, children }: SectionProps) {
  return (
    <nldd-container gap="8">
      <nldd-title
        size={4}
        text={title}
        heading-level={2}
        {...(supportingText ? { 'supporting-text': supportingText } : {})}
      >
        {action ? (
          <Button
            slot="end"
            size="sm"
            text={action.text}
            appearance={action.appearance ?? 'secondary'}
            onClick={action.onClick}
            {...(action.accessibleLabel ? { accessibleLabel: action.accessibleLabel } : {})}
          />
        ) : null}
      </nldd-title>
      {children}
    </nldd-container>
  );
}

interface FactProps {
  label: string;
  value: string;
  supportingText?: string;
}

/** One fact as a row: what it is above, the value below. */
export function Fact({ label, value, supportingText }: FactProps) {
  return (
    <nldd-list-item>
      <nldd-text-cell
        overline={label}
        text={value}
        {...(supportingText ? { 'supporting-text': supportingText } : {})}
      />
    </nldd-list-item>
  );
}

/** A framed list of facts. */
export function Facts({ label, children }: { label: string; children: ReactNode }) {
  return (
    <nldd-list accessible-label={label} appearance="box-base" type="form">
      {children}
    </nldd-list>
  );
}
