import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { PHASE_LABELS, STATUS_COLORS, statusLabel, type Phase } from '@/features/assignments/labels';
import { referenceText } from '@/features/assignments/financeText';
import { assignmentTabPath } from '@/features/assignments/paths';
import { FigureCells, FigureHeaderCells, FIGURE_COLUMNS } from '@/features/assignments/FigureCells';
import { EmptyNotice, ErrorNotice, Loading, Page, Section, Stack } from '@/ui/layout';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { ActionBar } from '@/ui/ActionBar';
import { fetchOverview, hasFigures, overviewKeys, type Figures, type OverviewRow } from './api';
import { YEAR_FILTER_LABEL, currentYearChoice, periodLabel, yearOptions } from './years';

/** Running work first; pipeline and closed work each in a table of their own. */
const PHASE_ORDER: readonly Phase[] = ['active', 'potential', 'closed'];

const PHASE_NOTE: Partial<Record<Phase, string>> = {
  potential:
    'Deze opdrachten zijn nog niet akkoord. Hun bedragen zijn een verwachting en tellen niet mee in de totalen van lopend werk.',
};

function PhaseTable({
  phase,
  rows,
  subtotal,
  period,
}: {
  phase: Phase;
  rows: OverviewRow[];
  subtotal: Figures | undefined;
  period: string;
}) {
  const showAmounts = hasFigures(subtotal);
  const note = PHASE_NOTE[phase];
  return (
    <Section title={PHASE_LABELS[phase]} {...(note && showAmounts ? { description: note } : {})}>
      <nldd-table
        accessible-label={`${PHASE_LABELS[phase]}, stand over ${period}`}
        columns={`minmax(220px,2fr) 170px${showAmounts ? ` ${FIGURE_COLUMNS}` : ' minmax(160px,1fr)'}`}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Opdracht" />
          <nldd-text-cell text="Status" />
          {showAmounts ? <FigureHeaderCells /> : <nldd-text-cell text="Opdrachtgever" />}
        </nldd-table-row>
        {rows.map((row) => (
          <nldd-table-row key={row.assignment_id}>
            <nldd-cell>
              <nldd-link
                href={assignmentTabPath(
                  row.assignment_id,
                  hasFigures(row.figures) ? 'finance' : 'overview',
                )}
                text={row.name}
              />
            </nldd-cell>
            <nldd-text-cell
              text={statusLabel(row.status)}
              {...(showAmounts && phase !== 'potential'
                ? { 'supporting-text': referenceText(row.reference_month) }
                : {})}
              color={STATUS_COLORS[row.status] === 'critical' ? 'critical' : 'content'}
            />
            {showAmounts ? (
              <FigureCells
                figures={hasFigures(row.figures) ? row.figures : null}
                error={row.pricing_error}
              />
            ) : (
              <nldd-text-cell text={row.client_name ?? ''} />
            )}
          </nldd-table-row>
        ))}
        {showAmounts && (
          <nldd-table-row>
            <nldd-text-cell text={`**Subtotaal ${PHASE_LABELS[phase].toLowerCase()}**`} />
            <nldd-text-cell />
            <FigureCells figures={subtotal} bold />
          </nldd-table-row>
        )}
      </nldd-table>
    </Section>
  );
}

/**
 * Stand van zaken: what state the money is in, per assignment. Potential
 * assignments stand apart with their own subtotal, so pipeline is never
 * read as committed work.
 */
export function OverviewPage() {
  const instance = useInstance();
  const [year, setYear] = useState(currentYearChoice);
  const contentRef = useRef<HTMLDivElement>(null);
  useRouterLinks(contentRef);

  const query = useQuery({ queryKey: overviewKeys.list(year), queryFn: () => fetchOverview(year) });
  const rows = query.data?.rows ?? [];
  const subtotals: Record<Phase, Figures | undefined> = {
    potential: query.data?.figures_potential,
    active: query.data?.figures_active,
    closed: query.data?.figures_closed,
  };
  const period = periodLabel(year);

  return (
    <Page title="Stand van zaken" instanceName={instance?.name} spacing="sections">
      <div ref={contentRef}>
        <Stack gap="section">
          <ActionBar
            label="Stand van zaken: periode"
            filters={[
              {
                label: YEAR_FILTER_LABEL,
                value: year,
                onChange: setYear,
                options: yearOptions(),
                width: '180px',
              },
            ]}
          />
          {query.isPending && <Loading />}
          {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
          {query.isSuccess && rows.length === 0 && (
            <EmptyNotice
              text="Er zijn geen opdrachten om te tonen"
              supportingText="Je ziet hier de opdrachten waar je bij betrokken bent."
            />
          )}
          {PHASE_ORDER.map((phase) => {
            const inPhase = rows.filter((row) => row.phase === phase);
            if (inPhase.length === 0) return null;
            return (
              <PhaseTable
                key={phase}
                phase={phase}
                rows={inPhase}
                subtotal={subtotals[phase]}
                period={period}
              />
            );
          })}
        </Stack>
      </div>
    </Page>
  );
}
