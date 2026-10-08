import { useEffect, useRef } from 'react';
import { useNlddEvent } from '@/components/nldd/events';

export interface PanelItem {
  key: string;
  text: string;
  /** The action on this item, when the reader may take one. */
  action?: { text: string; onClick: () => void };
}

interface CellPanelProps {
  /** Changes when another cell is chosen; the panel then takes focus. */
  cellKey: string;
  title: string;
  summary: string;
  items: PanelItem[];
  /** One action about the cell as a whole, e.g. a new inzet from that month. */
  action?: { text: string; onClick: () => void };
}

function PanelButton({ text, label, onClick }: { text: string; label: string; onClick: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return <nldd-button ref={ref} size="sm" appearance="secondary" text={text} accessible-label={label} />;
}

/**
 * What is in the cell the keyboard chose, with a button per bar. This is how
 * every bar of the timeline is reached and acted on without a pointer.
 */
export function CellPanel({ cellKey, title, summary, items, action }: CellPanelProps) {
  const ref = useRef<HTMLDivElement>(null);
  // An effect and not an animation frame: a frame never comes in a tab that
  // is not being painted.
  useEffect(() => {
    ref.current?.focus();
  }, [cellKey]);
  return (
    <div ref={ref} tabIndex={-1} role="region" aria-label="Inzet in de gekozen maand">
      <nldd-container gap="8">
        <nldd-title size={4} heading-level={2} text={title} />
        {summary && <nldd-text color="secondary">{summary}</nldd-text>}
        {items.length > 0 && (
          <nldd-table accessible-label="Inzet in deze maand" columns="minmax(280px,1fr) 160px">
            <nldd-table-row slot="header">
              <nldd-text-cell text="Inzet" />
              <nldd-text-cell text="Actie" />
            </nldd-table-row>
            {items.map((item) => (
              <nldd-table-row key={item.key}>
                <nldd-text-cell text={item.text} />
                <nldd-cell>
                  {item.action && (
                    <PanelButton
                      text={item.action.text}
                      label={`${item.action.text}: ${item.text}`}
                      onClick={item.action.onClick}
                    />
                  )}
                </nldd-cell>
              </nldd-table-row>
            ))}
          </nldd-table>
        )}
        {action && (
          <div>
            <PanelButton text={action.text} label={action.text} onClick={action.onClick} />
          </div>
        )}
      </nldd-container>
    </div>
  );
}
