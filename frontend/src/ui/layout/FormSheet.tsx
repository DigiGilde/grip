/**
 * A form in a side sheet: the one pattern for adding or changing something.
 *
 * Follows the design system's "bewerken in een sheet": the way out in the
 * title bar, the fields at one distance, one primary action under the last
 * field. The sheet stays in the document while closed, so its animation runs
 * and focus returns to the control that opened it.
 *
 * Rules that go with it:
 *   - Nothing that adds or changes is open by default. A section shows what
 *     is, with at most one action; the action opens this sheet.
 *   - Validate on submit, never before the user has typed.
 *   - One primary action. "Annuleer" sits in the title bar, away from it.
 */
import { useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { orUndef, useNlddEvent } from '@/components/nldd/events';

if (import.meta.env.MODE !== 'test') void import('./register');

/** Native validation bubbles would appear before submit; the form validates itself. */
const NO_NATIVE_VALIDATION: object = { novalidate: '' };

/** Width per kind of content, so sheets of one kind are equally wide. */
const WIDTH = {
  /** A handful of fields. */
  form: '480px',
  /** A form with a table or a preview in it. */
  wide: '640px',
} as const;

interface FormSheetProps {
  open: boolean;
  title: string;
  /** What the primary button does, in the words of the action that opened the sheet. */
  submitText: string;
  onSubmit: () => void;
  onClose: () => void;
  busy?: boolean;
  /** Shown above the fields after a failed submit. */
  error?: string | null;
  size?: keyof typeof WIDTH;
  children: ReactNode;
}

interface SubmitButtonProps {
  text: string;
  loading?: boolean;
}

function SubmitButton({ text, loading }: SubmitButtonProps) {
  return <nldd-button appearance="primary" type="submit" text={text} loading={orUndef(loading)} />;
}

export function FormSheet({
  open,
  title,
  submitText,
  onSubmit,
  onClose,
  busy,
  error,
  size = 'form',
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
    <nldd-sheet ref={sheetRef} open={orUndef(open)} placement="right" width={WIDTH[size]}>
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
          <nldd-container gap="24">
            {error ? <nldd-banner variant="critical" size="sm" text={error} /> : null}
            <nldd-form ref={formRef} {...NO_NATIVE_VALIDATION}>
              {/* nldd-form moves its direct children into its own form element.
                  React then loses track of siblings it wants to insert before,
                  and a field that appears conditionally blanks the page. One
                  stable wrapper that React owns keeps the fields together, and
                  it spaces them, since the form now has one child to space. */}
              <FormFields>{children}</FormFields>
              <nldd-form-actions>
                <nldd-button-group>
                  <SubmitButton text={submitText} loading={busy} />
                </nldd-button-group>
              </nldd-form-actions>
            </nldd-form>
          </nldd-container>
        </nldd-simple-section>
      </nldd-page>
    </nldd-sheet>,
    document.body,
  );
}

/**
 * The fields of a form at one distance. Use it for a form on a page too, as
 * the single direct child of nldd-form.
 */
export function FormFields({ children }: { children: ReactNode }) {
  return <nldd-container gap="20">{children}</nldd-container>;
}
