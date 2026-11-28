/**
 * Rows that each lead somewhere: the parts of a thing, the entries of a
 * section. A row says what it is in one line, what is the matter in a quiet
 * line under it, and a row with an address ends in the mark that it opens.
 */
import { RouterLinks } from '@/layout/RouterLinks';
import { IconCell } from './Icon';
import { Quiet } from './layout/primitives';

export interface LinkRow {
  key: string;
  text: string;
  /** Where the row leads. A row without one is only read. */
  href?: string;
  /** What is the matter, quiet, under the text. */
  notice?: string;
  /** A status that belongs to the row; the colour repeats what the text says. */
  tag?: { text: string; color: 'neutral' | 'success' | 'warning' | 'critical' | 'accent' };
  /** A short value at the end of the row: an amount, a count. */
  end?: string;
}

interface LinkRowsProps {
  /** Accessible name of the list. */
  label: string;
  rows: readonly LinkRow[];
}

export function LinkRows({ label, rows }: LinkRowsProps) {
  return (
    <RouterLinks>
      <nldd-list accessible-label={label}>
        {rows.map((row) => (
          <nldd-list-item key={row.key} {...(row.href ? { href: row.href } : {})}>
            <nldd-text-cell
              text={row.text}
              {...(row.notice ? { 'supporting-text': row.notice } : {})}
            />
            {row.tag && (
              <nldd-cell>
                <nldd-badge size="sm" color={row.tag.color} text={row.tag.text} />
              </nldd-cell>
            )}
            {row.end && (
              <nldd-cell horizontal-alignment="right">
                <Quiet>{row.end}</Quiet>
              </nldd-cell>
            )}
            {row.href && <IconCell concept="open" />}
          </nldd-list-item>
        ))}
      </nldd-list>
    </RouterLinks>
  );
}
