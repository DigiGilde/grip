/**
 * Row actions, one pattern for every table.
 *
 * The row itself is the way to open or edit: `OpenRow` makes the whole row
 * activate, and `OpenCell` is the name in it that a keyboard reaches.
 * Everything else a row can do sits behind one quiet icon button at the end
 * of the row, `RowActions`, in a column of the fixed width
 * `ROW_ACTIONS_COLUMN`, so the column before it ends on the same position in
 * every row. A destructive item asks for confirmation and says what goes
 * with it. No "Acties" header and no text buttons in a row.
 */
import { useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { orUndef, useNlddEvent } from '@/components/nldd/events';

/** The track for the actions column in a table's `columns`. */
export const ROW_ACTIONS_COLUMN = '48px';

export interface RowAction {
  text: string;
  /** Called when the item is chosen; after the confirmation when there is one. */
  onSelect?: () => void;
  /** A link instead of an action, e.g. to the inzet of this line. */
  href?: string;
  /** Marks the item as destructive in the menu. */
  destructive?: boolean;
  /** Asked before `onSelect`: what happens, and what goes with it. */
  confirm?: { text: string; supportingText?: string; confirmText: string };
}

function MenuItem({ action, onChoose }: { action: RowAction; onChoose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', action.href ? undefined : onChoose);
  return (
    <nldd-menu-item
      ref={ref}
      text={action.text}
      destructive={orUndef(action.destructive)}
      {...(action.href ? { href: action.href } : {})}
    />
  );
}

function DialogButton({
  text,
  appearance,
  onClick,
}: {
  text: string;
  appearance: 'secondary' | 'destructive';
  onClick: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return <nldd-button ref={ref} slot="actions" text={text} appearance={appearance} />;
}

interface RowActionsProps {
  /** The name of the row, for "Meer acties voor <name>". */
  name: string;
  actions: readonly RowAction[];
}

/** The last cell of a row: one quiet button with the menu of what else the row can do. */
export function RowActions({ name, actions }: RowActionsProps) {
  const [asking, setAsking] = useState<RowAction | null>(null);
  const dialogRef = useRef<HTMLElement>(null);
  useNlddEvent(dialogRef, 'close', () => setAsking(null));
  // The dialog keeps its last text while it animates out.
  const [lastAsked, setLastAsked] = useState<RowAction | null>(null);
  if (asking && asking !== lastAsked) setLastAsked(asking);
  const shown = asking ?? lastAsked;

  if (actions.length === 0) return <nldd-cell />;
  return (
    <nldd-cell>
      <nldd-icon-button
        icon="more"
        size="sm"
        appearance="neutral-transparent"
        popup-type="menu"
        accessible-label={`Meer acties voor ${name}`}
        text={`Meer acties voor ${name}`}
      >
        <nldd-menu slot="popup" placement="bottom-end">
          {actions.map((action) => (
            <MenuItem
              key={action.text}
              action={action}
              onChoose={() => (action.confirm ? setAsking(action) : action.onSelect?.())}
            />
          ))}
        </nldd-menu>
      </nldd-icon-button>
      {createPortal(
        <nldd-modal-dialog
          ref={dialogRef}
          variant="alert"
          open={orUndef(asking !== null)}
          text={shown?.confirm?.text ?? ''}
          {...(shown?.confirm?.supportingText
            ? { 'supporting-text': shown.confirm.supportingText }
            : {})}
        >
          <DialogButton text="Annuleer" appearance="secondary" onClick={() => setAsking(null)} />
          <DialogButton
            text={shown?.confirm?.confirmText ?? ''}
            appearance="destructive"
            onClick={() => {
              const action = asking;
              setAsking(null);
              action?.onSelect?.();
            }}
          />
        </nldd-modal-dialog>,
        document.body,
      )}
    </nldd-cell>
  );
}

/** Controls inside a row that have their own action; a click on them is not the row's. */
const OWN_CONTROLS = 'nldd-icon-button, nldd-button, nldd-menu, nldd-menu-item, nldd-link, a, button';

interface OpenRowProps {
  /** Opens or edits what the row stands for. */
  onOpen?: () => void;
  children: ReactNode;
}

/** A table row that opens on a click anywhere in it. Without `onOpen` a plain row. */
export function OpenRow({ onOpen, children }: OpenRowProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(
    ref,
    'click',
    onOpen
      ? (event) => {
          const path = event.composedPath();
          const own = path.some(
            (node) => node instanceof Element && node !== ref.current && node.matches(OWN_CONTROLS),
          );
          if (!own) onOpen();
        }
      : undefined,
  );
  return (
    <nldd-table-row ref={ref} {...(onOpen ? { style: { cursor: 'pointer' } } : {})}>
      {children}
    </nldd-table-row>
  );
}

interface OpenCellProps {
  /** The name of the row: the role of a line, the name of a person. */
  text: string;
  /** The facts under it, as one quiet line. */
  supportingText?: string;
  /** What activating the name does, for a screen reader: "Bewerk <name>". */
  accessibleLabel?: string;
  onOpen?: () => void;
  /** A small element at the end of the quiet line, e.g. a tag. */
  children?: ReactNode;
}

/** The first cell of a row: the name, which a keyboard activates with Enter. */
export function OpenCell({ text, supportingText, accessibleLabel, onOpen, children }: OpenCellProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(
    ref,
    'click',
    onOpen
      ? (event) => {
          event.preventDefault();
          onOpen();
        }
      : undefined,
  );
  return (
    <nldd-cell>
      <nldd-container gap="4">
        {onOpen ? (
          <nldd-link
            ref={ref}
            href="#"
            text={text}
            {...(accessibleLabel ? { 'accessible-label': accessibleLabel } : {})}
          />
        ) : (
          <nldd-text>{text}</nldd-text>
        )}
        {(supportingText || children) && (
          <nldd-container layout="row" gap="8">
            {supportingText && (
              <nldd-text color="secondary" size="sm">
                {supportingText}
              </nldd-text>
            )}
            {children}
          </nldd-container>
        )}
      </nldd-container>
    </nldd-cell>
  );
}
