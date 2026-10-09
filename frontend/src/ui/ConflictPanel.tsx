/**
 * What a form shows when its save was refused because the record changed
 * (see `@/ui/stale`).
 */
import { Button } from '@/ui/Button';
import { Quiet, Stack } from '@/ui/layout';
import type { ConflictValue, StaleConflict } from '@/ui/stale';

interface ConflictPanelProps {
  conflict: StaleConflict;
  /**
   * What stands in the record now, in the words of the form. Left out by a
   * form that does not compare field by field: the page behind it shows it.
   */
  theirs?: readonly ConflictValue[];
  /** What the person filled in. */
  mine?: readonly ConflictValue[];
  /** Save the own values on top of what stands there now. */
  onKeepMine: () => void;
  /** Drop the own values and continue from what stands there now. */
  onTakeTheirs: () => void;
  busy?: boolean;
}

/**
 * What a form shows when its save was refused because the record changed:
 * only the fields that differ, theirs next to the person's own, and the two
 * ways on.
 */
export function ConflictPanel({
  conflict,
  theirs,
  mine,
  onKeepMine,
  onTakeTheirs,
  busy = false,
}: ConflictPanelProps) {
  const own = new Map((mine ?? []).map((item) => [item.label, item.value]));
  const differing = (theirs ?? []).filter((item) => (own.get(item.label) ?? '') !== item.value);
  return (
    <div data-conflict>
      <Stack gap="related">
        <nldd-banner
          variant="warning"
          size="sm"
          text={conflict.message}
          supporting-text="Wat je invulde staat nog in het formulier. Kies wat blijft."
        />
        {differing.length > 0 ? (
          <nldd-table
            accessible-label="Wat er nu staat naast wat jij invulde"
            columns="minmax(120px,1fr) minmax(120px,1fr) minmax(120px,1fr)"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Veld" />
              <nldd-text-cell text="Staat er nu" />
              <nldd-text-cell text="In jouw formulier" />
            </nldd-table-row>
            {differing.map((item) => (
              <nldd-table-row key={item.label}>
                <nldd-text-cell text={item.label} />
                <nldd-text-cell text={item.value || 'Leeg'} />
                <nldd-text-cell text={own.get(item.label) || 'Leeg'} />
              </nldd-table-row>
            ))}
          </nldd-table>
        ) : theirs ? (
          <Quiet>Wat er nu staat is gelijk aan wat jij invulde.</Quiet>
        ) : null}
        {differing.length > 0 ? (
          <Quiet>
            Bewaar je jouw wijziging, dan komt in deze velden wat in jouw formulier staat.
          </Quiet>
        ) : null}
        <nldd-button-group>
          <Button text="Bewaar mijn wijziging" disabled={busy} onClick={onKeepMine} />
          <Button text="Neem de andere over" disabled={busy} onClick={onTakeTheirs} />
        </nldd-button-group>
      </Stack>
    </div>
  );
}
