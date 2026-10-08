import { useId, useLayoutEffect, useRef, type FormEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { useFormMessage } from '@/ui/layout/formMessage';
import { Button } from './controls';
import './nldd';

interface SheetProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Text of the way out in the title bar. */
  dismissText?: string;
  width?: string;
}

/**
 * A side sheet holding a whole page: a title bar with the way out, a heading
 * and the content. It stays in the document while closed, as the design
 * system asks, and renders at the document root so it does not take height
 * from the pane it was opened from.
 *
 * The element that had focus when the sheet opened gets it back on close.
 */
export function Sheet({
  open,
  title,
  onClose,
  children,
  dismissText = 'Sluit',
  width = '560px',
}: SheetProps) {
  const ref = useRef<HTMLElement>(null);
  const opener = useRef<Element | null>(null);
  const titleId = useId();
  useNlddEvent(ref, 'close', () => onClose());

  // A layout effect: it runs in the same commit that sets `open`, before the
  // sheet has moved focus into itself, so it still sees what opened it.
  useLayoutEffect(() => {
    if (open) {
      opener.current = document.activeElement;
    } else if (opener.current instanceof HTMLElement && opener.current !== document.body) {
      opener.current.focus();
      opener.current = null;
    }
  }, [open]);

  return createPortal(
    <nldd-sheet ref={ref} open={orUndef(open)} placement="right" width={width}>
      <nldd-page>
        <nldd-top-title-bar
          slot="header"
          text={title}
          dismiss-text={dismissText}
          collapse-anchor={titleId}
        />
        <nldd-simple-section>
          <nldd-title id={titleId} slot="header" size={2} text={title} heading-level={1} />
          {/* Content only while open: a closed sheet holds no stale form. */}
          {open ? children : null}
        </nldd-simple-section>
      </nldd-page>
    </nldd-sheet>,
    document.body,
  );
}

interface FormProps {
  onSubmit: () => void;
  submitText: string;
  submitting?: boolean;
  error?: string | null;
  children: ReactNode;
}

/**
 * A form with its one action under the last field. The native form is our
 * own child, so React keeps control of the fields and Enter submits.
 */
export function Form({ onSubmit, submitText, submitting, error, children }: FormProps) {
  const formRef = useRef<HTMLFormElement>(null);
  // The message goes once the reader changes a field; see useFormMessage.
  const message = useFormMessage(formRef, error);
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    message.submitted();
    if (!submitting) onSubmit();
  };
  return (
    <nldd-form>
      <form ref={formRef} onSubmit={handleSubmit} noValidate>
        {message.shown ? <nldd-banner variant="critical" text={message.shown} /> : null}
        {children}
        <nldd-form-actions>
          <nldd-button-group>
            <Button appearance="primary" type="submit" text={submitText} loading={submitting} />
          </nldd-button-group>
        </nldd-form-actions>
      </form>
    </nldd-form>
  );
}

interface ConfirmProps {
  open: boolean;
  text: string;
  supportingText: string;
  confirmText: string;
  onConfirm: () => void;
  onClose: () => void;
  destructive?: boolean;
}

/** A modal for a decision that deserves a moment, with the way back first. */
export function ConfirmDialog({
  open,
  text,
  supportingText,
  confirmText,
  onConfirm,
  onClose,
  destructive,
}: ConfirmProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'close', () => onClose());
  return createPortal(
    <nldd-modal-dialog
      ref={ref}
      open={orUndef(open)}
      variant="alert"
      text={text}
      supporting-text={supportingText}
    >
      <Button slot="actions" text="Annuleer" onClick={onClose} />
      <Button
        slot="actions"
        appearance={destructive ? 'destructive' : 'primary'}
        text={confirmText}
        onClick={onConfirm}
      />
    </nldd-modal-dialog>,
    document.body,
  );
}
