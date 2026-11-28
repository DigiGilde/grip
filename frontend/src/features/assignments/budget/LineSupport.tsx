import { useRef, useState } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { referenceStateText } from '@/features/costs/costText';
import { formatEuro, formatPercent, formatPeriod } from '@/lib/format';
import { IconCell } from '@/ui/Icon';
import { Section } from '@/ui/layout';
import type { AssignmentFinance, FinanceLine } from '../financeApi';
import { FIGURE_LABELS } from '../financeText';

// The chevron turns with the row. Spread as a plain attribute because the
// package types do not list it on the icon cell.
const DISCLOSURE: object = { disclosure: '' };

/** One line that opens to the amounts behind it. */
function LineDetail({ line }: { line: FinanceLine }) {
  const [expanded, setExpanded] = useState(false);
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', (event) => {
    // Only the row itself toggles; a click inside the opened detail does not.
    const target = event.target as Element | null;
    if (target?.closest('nldd-list-item') === ref.current) setExpanded((open) => !open);
  });
  const figures = line.figures;
  const summary = figures
    ? `${formatEuro(figures.realised_cents)} gerealiseerde inzet, ${formatEuro(figures.planned_cents)} nog gepland, ${formatEuro(figures.costs_cents)} kosten`
    : (line.pricing_error ?? 'Niet berekend');
  return (
    <nldd-list-item ref={ref} button expanded={orUndef(expanded)}>
      <IconCell concept="open" {...DISCLOSURE} />
      <nldd-spacer-cell size="8" />
      <nldd-text-cell text={line.description} supporting-text={summary} />
      <nldd-text-cell
        width="fit-content"
        text={figures ? formatEuro(figures.expected_total_cents) : ''}
        supporting-text={figures ? FIGURE_LABELS.expected : ''}
        horizontal-alignment="right"
      />
      {line.persons.map((person) => (
        <nldd-list-item slot="children" key={person.allocation_id}>
          <nldd-spacer-cell size="44" />
          <nldd-text-cell
            text={person.person_name}
            supporting-text={[
              formatPeriod(person.start_date, person.end_date),
              person.category_mismatch ? 'andere categorie dan de regel aanneemt' : '',
            ]
              .filter(Boolean)
              .join(', ')}
          />
          <nldd-text-cell
            width="fit-content"
            text={formatEuro(person.total_cents)}
            supporting-text={`${formatEuro(person.realised_cents)} gerealiseerde inzet, ${formatEuro(person.planned_cents)} gepland`}
            horizontal-alignment="right"
          />
        </nldd-list-item>
      ))}
      {line.persons_hidden > 0 && (
        <nldd-list-item slot="children">
          <nldd-spacer-cell size="44" />
          <nldd-text-cell
            text={
              line.persons_hidden === 1
                ? 'De inzet van 1 persoon zit in het totaal; het bedrag per persoon is voor jou niet zichtbaar'
                : `De inzet van ${line.persons_hidden} personen zit in het totaal; de bedragen per persoon zijn voor jou niet zichtbaar`
            }
          />
        </nldd-list-item>
      )}
      {line.costs.map((cost) => (
        <nldd-list-item slot="children" key={cost.cost_item_id}>
          <nldd-spacer-cell size="44" />
          <nldd-text-cell
            text={cost.description}
            supporting-text={`Kostenpost, ${formatPercent(cost.pct)} gedekt door deze regel`}
          />
          {cost.reference_state && cost.reference_state !== 'found' ? (
            <nldd-text-cell
              width="fit-content"
              text={referenceStateText(cost.reference_state, cost.executor_name)}
              horizontal-alignment="right"
            />
          ) : (
            <nldd-text-cell
              width="fit-content"
              text={formatEuro(cost.total_cents)}
              supporting-text={`${formatEuro(cost.realised_cents)} gerealiseerd, ${formatEuro(cost.forecast_cents)} ingeschat`}
              horizontal-alignment="right"
            />
          )}
        </nldd-list-item>
      ))}
      {figures &&
        line.persons.length === 0 &&
        line.persons_hidden === 0 &&
        line.costs.length === 0 && (
          <nldd-list-item slot="children">
            <nldd-spacer-cell size="44" />
            <nldd-text-cell
              text="Op deze regel staat geen inzet en geen kostendekking"
            />
          </nldd-list-item>
        )}
    </nldd-list-item>
  );
}

/** What stands behind each line: who works on it and which costs it covers. */
export function LineSupport({ finance }: { finance: AssignmentFinance }) {
  if (finance.lines.length === 0) return null;
  return (
    <Section title="Onderbouwing per regel">
      <nldd-list
        type="tree"
        appearance="box-base"
        accessible-label="Onderbouwing per begrotingsregel"
      >
        {finance.lines.map((line) => (
          <LineDetail key={line.budget_line_id} line={line} />
        ))}
      </nldd-list>
    </Section>
  );
}
