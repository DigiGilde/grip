import { formatEuro } from '@/lib/format';
import { NameLine, Quiet, Section, Stack } from '@/ui/layout';
import type { StandBudget } from './api';
import { budgetLineSummary } from './words';

const CHANGE_WORDS = { added: 'Nieuw', changed: 'Gewijzigd' } as const;

/** The budget as it stood, with what this moment did to it marked in place. */
export function StandBudgetPart({ budget }: { budget: StandBudget }) {
  const { lines, removed } = budget;
  if (lines.length === 0 && removed.length === 0) return null;
  const showMoney =
    budget.total_budgeted_cents !== undefined ||
    lines.some((line) => line.budgeted_cents !== undefined);
  const years = Object.entries(budget.subtotals_by_year ?? {}).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  const total = budget.total_budgeted_cents;
  const previous = budget.previous_total_cents;
  return (
    <Section title="Begroting" level={3}>
      <Stack gap="close">
        {lines.length > 0 && (
          <nldd-table
            accessible-label="Begrotingsregels"
            columns={`minmax(240px,2fr)${showMoney ? ' 150px' : ''}`}
            sm-columns={`minmax(0,1fr)${showMoney ? ' 110px' : ''}`}
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Regel" />
              {showMoney && <nldd-text-cell text="Begroot" horizontal-alignment="right" />}
            </nldd-table-row>
            {lines.map((line) => {
              const summary = budgetLineSummary(line);
              return (
                <nldd-table-row key={line.id}>
                  <nldd-cell>
                    <NameLine
                      badges={
                        line.change ? (
                          <nldd-badge color="neutral" text={CHANGE_WORDS[line.change]} />
                        ) : undefined
                      }
                      detail={summary || undefined}
                    >
                      <nldd-text>
                        <span>{line.description}</span>
                      </nldd-text>
                    </NameLine>
                  </nldd-cell>
                  {showMoney && (
                    <nldd-text-cell
                      text={
                        line.budgeted_cents === null
                          ? 'Niet berekend'
                          : formatEuro(line.budgeted_cents)
                      }
                      horizontal-alignment="right"
                    />
                  )}
                </nldd-table-row>
              );
            })}
            {showMoney &&
              // One year: the subtotal is the total, so it is said once.
              years.length > 1 &&
              years.map(([year, cents]) => (
                <nldd-table-row key={`year-${year}`}>
                  <nldd-text-cell text={`**Subtotaal ${year}**`} />
                  <nldd-text-cell text={`**${formatEuro(cents)}**`} horizontal-alignment="right" />
                </nldd-table-row>
              ))}
            {showMoney && total != null && (
              <nldd-table-row>
                <nldd-text-cell text="**Totaal begroot**" />
                <nldd-text-cell
                  text={`**${formatEuro(total)}**`}
                  horizontal-alignment="right"
                  {...(previous != null
                    ? { 'supporting-text': `was ${formatEuro(previous)}` }
                    : {})}
                />
              </nldd-table-row>
            )}
          </nldd-table>
        )}
        {removed.length > 0 && <Quiet>Verwijderd: {removed.join(', ')}</Quiet>}
        {budget.pricing_error && <Quiet>{budget.pricing_error}</Quiet>}
      </Stack>
    </Section>
  );
}
