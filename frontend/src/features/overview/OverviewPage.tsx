import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import {
  NOTHING_PLANNED_TEXT,
  nothingPlanned,
  referenceText,
  varianceWord,
} from '@/features/assignments/financeText';
import {
  PHASE_LABELS,
  STATUS_COLORS,
  statusLabel,
  type Phase,
} from '@/features/assignments/labels';
import { assignmentPath, assignmentTabPath } from '@/features/assignments/paths';
import { Button } from '@/features/assignments/ui';
// The tiles are those of the Rapportage landing view, so the two pages look alike.
import '@/features/reports/reports.css';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatEuro, formatMonth } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import {
  KeyFigures,
  SignalList,
  EmptyNotice,
  ErrorNotice,
  Loading,
  NameLine,
  Page,
  Quiet,
  Section,
  Stack,
} from '@/ui/layout';
import { OpenRow } from '@/ui/RowActions';
import { fetchOverview, hasFigures, overviewKeys, type Figures, type OverviewRow } from './api';
import {
  attentionItems,
  rowsOfPhase,
  sharedReference,
  SORT_OPTIONS,
  sortRows,
  startTiles,
  type SortMode,
} from './model';
import { MyTasks } from './MyTasks';
import './overview.css';
import {
  WHOLE_PERIOD,
  YEAR_FILTER_LABEL,
  currentYearChoice,
  periodLabel,
  yearOptions,
} from './years';

/** How many attention points show before "Toon alle". */
const ATTENTION_LIMIT = 4;

/** Part 1: what needs the reader, each point a link to where it is solved. */
/** The status a phase implies; a row shows its status only when it says more. */
const PHASE_DEFAULT_STATUS: Record<Phase, string | undefined> = {
  potential: undefined,
  active: 'in_progress',
  closed: 'completed',
};

function Attention({ rows }: { rows: readonly OverviewRow[] }) {
  const [all, setAll] = useState(false);
  const items = attentionItems(rows);
  if (items.length === 0) return null;
  const shown = all ? items : items.slice(0, ATTENTION_LIMIT);
  return (
    <Section title="Wat vraagt aandacht">
      <Stack gap="related">
        {/* What is the matter as the link to where it is solved; under it, on what. */}
        <SignalList
          label="Wat vraagt aandacht"
          signals={shown.map((item) => ({
            key: item.key,
            text: item.text,
            href: item.href,
            detail: item.assignment,
            tone: item.tone,
          }))}
        />
        {items.length > shown.length && (
          <nldd-container layout="row">
            <Button text={`Toon alle ${items.length} punten`} onClick={() => setAll(true)} />
          </nldd-container>
        )}
      </Stack>
    </Section>
  );
}

/** The afwijking of one row: a small bar and the amount, with room or overrun in words. */
function VarianceCell({ figures }: { figures: Figures }) {
  // The server's percentage, only to size the bar; no amount is computed here.
  const pct = figures.variance_pct === null ? 0 : Number(figures.variance_pct);
  const used = Math.max(0, Math.min(100, 100 - pct));
  if (nothingPlanned(figures)) {
    return (
      <nldd-cell>
        <nldd-text size="sm" color="secondary">
          {NOTHING_PLANNED_TEXT}
        </nldd-text>
      </nldd-cell>
    );
  }
  return (
    <nldd-cell>
      <nldd-container gap="4">
        <span
          className={figures.overrun ? 'grip-variance grip-variance--over' : 'grip-variance'}
          aria-hidden="true"
        >
          <span className="grip-variance__fill" style={{ inlineSize: `${used}%` }} />
        </span>
        <nldd-text size="sm" {...(figures.overrun ? { color: 'critical' } : {})}>
          {/* Exactly on budget: the word says it, an amount of nothing does not. */}
          {figures.variance_cents === 0
            ? varianceWord(figures)
            : `${varianceWord(figures)} ${formatEuro(Math.abs(figures.variance_cents))}`}
        </nldd-text>
      </nldd-container>
    </nldd-cell>
  );
}

interface ListProps {
  phase: Phase;
  rows: readonly OverviewRow[];
  subtotal: Figures | undefined;
  period: string;
}

/** Part 3: the assignments of one phase, scannable without scrolling sideways. */
function AssignmentList({ phase, rows, subtotal, period }: ListProps) {
  const navigate = useNavigate();
  const money = hasFigures(subtotal);
  const reference = sharedReference(rows);
  return (
    <Stack gap="close">
      {money && phase !== 'potential' && reference !== undefined && (
        <Quiet>{referenceText(reference)}</Quiet>
      )}
      <nldd-table
        accessible-label={`${PHASE_LABELS[phase]}, ${period}`}
        columns={money ? 'minmax(220px,2fr) 120px 130px minmax(170px,1fr)' : 'minmax(220px,1fr)'}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Opdracht" />
          {money && <nldd-text-cell text="Begroot" horizontal-alignment="right" />}
          {money && <nldd-text-cell text="Verwacht totaal" horizontal-alignment="right" />}
          {money && <nldd-text-cell text="Afwijking" />}
        </nldd-table-row>
        {rows.map((row) => {
          const figures = hasFigures(row.figures) ? row.figures : null;
          return (
            <OpenRow
              key={row.assignment_id}
              onOpen={() => navigate(assignmentPath(row.assignment_id))}
            >
              <nldd-cell>
                <NameLine
                  badges={
                    // The section heading already says what phase this is;
                    // a status is news only where it says more than that.
                    row.status === PHASE_DEFAULT_STATUS[phase] ? undefined : (
                      <nldd-badge
                        size="sm"
                        color={STATUS_COLORS[row.status] ?? 'neutral'}
                        text={statusLabel(row.status)}
                      />
                    )
                  }
                  detail={
                    row.pricing_error ||
                    (money && phase !== 'potential' && reference === undefined && figures
                      ? row.reference_month
                        ? `Stand t/m ${formatMonth(row.reference_month)}`
                        : 'Nog geen maand afgesloten'
                      : undefined)
                  }
                >
                  <nldd-link
                    size="md"
                    href={
                      money
                        ? assignmentTabPath(row.assignment_id, 'finance')
                        : assignmentPath(row.assignment_id)
                    }
                    text={row.name}
                  />
                </NameLine>
              </nldd-cell>
              {money && (
                <nldd-text-cell
                  text={figures ? formatEuro(figures.budgeted_cents) : 'Niet berekend'}
                  horizontal-alignment="right"
                />
              )}
              {money && (
                <nldd-text-cell
                  text={figures ? formatEuro(figures.expected_total_cents) : ''}
                  horizontal-alignment="right"
                />
              )}
              {money && (figures ? <VarianceCell figures={figures} /> : <nldd-text-cell />)}
            </OpenRow>
          );
        })}
      </nldd-table>
      {/* A sum of nothing is not said. */}
      {money && subtotal && subtotal.budgeted_cents !== 0 && (
        <Quiet>
          {`${phase === 'potential' ? 'Als alles doorgaat' : 'Samen'}: ${formatEuro(subtotal.budgeted_cents)} begroot, ` +
            `${formatEuro(subtotal.expected_total_cents)} verwacht totaal, ` +
            `${varianceWord(subtotal).toLowerCase()} ${formatEuro(Math.abs(subtotal.variance_cents))}.`}
        </Quiet>
      )}
    </Stack>
  );
}

/**
 * The start page: what needs the reader, how running work stands, and the
 * assignments. Potential assignments stand apart, so pipeline is never read
 * as committed work. A reader without money rights gets the same page
 * without figures.
 */
export function OverviewPage() {
  const instance = useInstance();
  const [year, setYear] = useState(currentYearChoice);
  const [sort, setSort] = useState<SortMode>('attention');
  const [showClosed, setShowClosed] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  useRouterLinks(contentRef);

  const query = useQuery({ queryKey: overviewKeys.list(year), queryFn: () => fetchOverview(year) });
  const overview = query.data;
  const rows = overview?.rows ?? [];
  const period = periodLabel(year);
  const active = rowsOfPhase(rows, 'active');
  const potential = rowsOfPhase(rows, 'potential');
  const closed = rowsOfPhase(rows, 'closed');
  const leftOut = active.leftOut + potential.leftOut + closed.leftOut;
  const tiles = overview ? startTiles(overview, period, sharedReference(active.shown)) : [];
  const shownRows = [...active.shown, ...potential.shown, ...closed.shown];

  return (
    <Page title="Stand van zaken" instanceName={instance?.name}>
      <div ref={contentRef}>
        <Stack gap="group">
          <ActionBar
            label="Stand van zaken: periode en volgorde"
            filters={[
              {
                label: YEAR_FILTER_LABEL,
                value: year,
                onChange: setYear,
                options: yearOptions(),
                width: '180px',
              },
              {
                label: 'Volgorde',
                value: sort,
                onChange: (value) => setSort(value as SortMode),
                options: SORT_OPTIONS,
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
          {query.isSuccess && rows.length > 0 && (
            // What the reader must do first, then what asks attention; side by
            // side when there is room, one of them alone takes the row.
            <div className="grip-start">
              <MyTasks />
              <Attention rows={shownRows} />
            </div>
          )}
          {tiles.length > 0 && (
            <KeyFigures
              label={`Kerncijfers ${period}`}
              figures={tiles.map((tile) => ({
                label: tile.label,
                value: tile.value,
                detail: tile.attention ?? (tile.context || undefined),
                critical: Boolean(tile.attention),
              }))}
            />
          )}
          {active.shown.length > 0 && (
            <Section title={PHASE_LABELS.active}>
              <AssignmentList
                phase="active"
                rows={sortRows(active.shown, sort)}
                subtotal={overview?.figures_active}
                period={period}
              />
            </Section>
          )}
          {potential.shown.length > 0 && (
            <Section title={PHASE_LABELS.potential}>
              <AssignmentList
                phase="potential"
                rows={sortRows(potential.shown, sort)}
                subtotal={overview?.figures_potential}
                period={period}
              />
            </Section>
          )}
          {leftOut > 0 && (
            <Stack gap="close">
              <Quiet>
                {leftOut === 1
                  ? `1 opdracht loopt niet in ${period} en staat hier niet.`
                  : `${leftOut} opdrachten lopen niet in ${period} en staan hier niet.`}
              </Quiet>
              <nldd-container layout="row">
                <Button text="Toon de hele looptijd" onClick={() => setYear(WHOLE_PERIOD)} />
              </nldd-container>
            </Stack>
          )}
          {closed.shown.length > 0 && (
            <Stack gap="related">
              <nldd-container layout="row">
                <Button
                  text={
                    showClosed
                      ? 'Verberg afgesloten opdrachten'
                      : `Toon afgesloten opdrachten (${closed.shown.length})`
                  }
                  onClick={() => setShowClosed((current) => !current)}
                />
              </nldd-container>
              {showClosed && (
                <Section title={PHASE_LABELS.closed}>
                  <AssignmentList
                    phase="closed"
                    rows={sortRows(closed.shown, sort)}
                    subtotal={overview?.figures_closed}
                    period={period}
                  />
                </Section>
              )}
            </Stack>
          )}
        </Stack>
      </div>
    </Page>
  );
}
