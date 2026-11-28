import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNlddEvent } from '@/components/nldd/events';
import { incompleteText } from '@/features/costs/costText';
import { RouterLinks } from '@/layout/RouterLinks';
import { WHOLE_PERIOD, YEAR_FILTER_LABEL, periodLabel } from '@/features/overview/years';
import { formatEuro, formatPeriod } from '@/lib/format';
import { ActionBar, type ActionBarAction, type ActionBarOption } from '@/ui/ActionBar';
import { EmptyNotice, ErrorNotice, LoadError, Loading, Quiet, Stack } from '@/ui/layout';
import { OpenRow, ROW_ACTIONS_COLUMN, RowActions, RowActionsHeader } from '@/ui/RowActions';
import { assignmentKeys, fetchBudget, type AssignmentDetail, type BudgetLine } from '../api';
import { BudgetNotices } from '../BudgetEditor';
import { intendedText } from '../budgetForm';
import { FIGURE_COLUMNS, FigureCells, FigureHeaderCells } from '../FigureCells';
import {
  fetchAssignmentFinance,
  financeKeys,
  type AssignmentFinance,
  type KeyFigures,
} from '../financeApi';
import { rateCauseText, referenceText } from '../financeText';
import { assignmentPartPath } from '../paths';
import { useRateCards } from '../rateText';
import { useAssignmentFrame } from '../shell';
import { Attention } from './Attention';
import { LineSupport } from './LineSupport';
import { lineSummary } from './lineText';
import { MonthlyEffort } from './MonthlyEffort';
import { useLineActions } from './useLineActions';

/** The years the assignment runs in, then all of it. One year leaves nothing to choose. */
function yearChoices(assignment: AssignmentDetail): ActionBarOption[] {
  const first = Number(assignment.start_date?.slice(0, 4));
  const last = Number(assignment.end_date?.slice(0, 4));
  if (!first || !last || last <= first) return [];
  const years = Array.from({ length: last - first + 1 }, (_, index) => String(first + index));
  return [
    ...years.map((year) => ({ value: year, label: year })),
    { value: WHOLE_PERIOD, label: 'Hele looptijd' },
  ];
}

/** Over which period the table counts, and up to which month the amounts are real. */
function standText(assignment: AssignmentDetail, year: string, finance: AssignmentFinance): string {
  const scope =
    year === WHOLE_PERIOD
      ? ['Hele looptijd', formatPeriod(assignment.start_date, assignment.end_date)]
          .filter(Boolean)
          .join(', ')
      : `Over ${year}`;
  const reference = referenceText(finance.reference_month);
  return `${scope}. ${reference}${reference.endsWith('.') ? '' : '.'}`;
}

/** The signed quote against the budget. The server gives both over the whole period. */
function agreementText(key: KeyFigures, year: string): string | null {
  if (key.agreed_cents === null) return null;
  const differs = key.agreed_minus_budgeted_cents ?? 0;
  const scope = year === WHOLE_PERIOD ? '' : ' over de hele looptijd';
  // Said only when it differs; "gelijk" is no news.
  const difference =
    differs > 0
      ? `, ${formatEuro(differs)} hoger dan de begroting`
      : differs < 0
        ? `, ${formatEuro(-differs)} lager dan de begroting`
        : '';
  return `Offerte met akkoord${scope}: ${formatEuro(key.agreed_cents)}${difference}.`;
}

/**
 * The name of a line with its one quiet line, at the size of the figures next
 * to it. For who may open the line, the name is what a keyboard reaches.
 */
function LineName({
  name,
  support,
  onOpen,
}: {
  name: string;
  support: string;
  onOpen: (() => void) | undefined;
}) {
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
    <nldd-text-cell
      row-header
      {...(onOpen ? {} : { text: name })}
      {...(support ? { 'supporting-text': support } : {})}
    >
      {onOpen && (
        <p>
          <nldd-link ref={ref} href="#" text={name} accessible-label={`Bewerk ${name}`} />
        </p>
      )}
    </nldd-text-cell>
  );
}

interface StandTableProps {
  assignment: AssignmentDetail;
  finance: AssignmentFinance;
  period: string;
  /** The lines as they are saved: what the sheet edits, and their FTE for who may see it. */
  saved: readonly BudgetLine[];
  canEdit: boolean;
  onOpenLine: (line: BudgetLine) => void;
}

/** Every amount of the rule per line, with the total of the service under them. */
function StandTable({ assignment, finance, period, saved, canEdit, onOpenLine }: StandTableProps) {
  const rates = useRateCards();
  const { actionsOf, problem } = useLineActions(assignment.id);
  const parent = { start: assignment.start_date, end: assignment.end_date };
  return (
    <>
      {problem && <ErrorNotice message={problem} />}
      <nldd-table
        accessible-label={`Stand per begrotingsregel, ${period}`}
        columns={`minmax(190px,3fr) ${FIGURE_COLUMNS}${canEdit ? ` ${ROW_ACTIONS_COLUMN}` : ''}`}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Regel" />
          <FigureHeaderCells />
          {canEdit && <RowActionsHeader />}
        </nldd-table-row>
        {finance.lines.map((line) => {
          const detail = saved.find((item) => item.id === line.budget_line_id);
          const open = canEdit && detail ? () => onOpenLine(detail) : undefined;
          return (
            <OpenRow key={line.budget_line_id} {...(open ? { onOpen: open } : {})}>
              <LineName
                name={line.description}
                onOpen={open}
                support={[
                  detail
                    ? lineSummary(detail, rates.name, parent)
                    : line.rate_category
                      ? rates.name(line.rate_category)
                      : '',
                  detail ? intendedText(detail) : '',
                  // The cause of a rate difference next to the line it explains.
                  rateCauseText(line),
                  line.incomplete_by.length > 0 ? incompleteText(line.incomplete_by) : '',
                ]
                  .filter(Boolean)
                  .join('. ')}
              />
              <FigureCells
                figures={line.figures}
                error={line.pricing_error}
                withoutPlan={line.kind === 'personnel'}
              />
              {canEdit &&
                (detail ? (
                  <RowActions name={line.description} actions={actionsOf(detail)} />
                ) : (
                  <nldd-cell />
                ))}
            </OpenRow>
          );
        })}
        <nldd-table-row>
          <nldd-text-cell
            row-header
            text="**Totaal**"
            {...(finance.incomplete_by.length > 0
              ? { 'supporting-text': incompleteText(finance.incomplete_by) }
              : {})}
          />
          <FigureCells figures={finance.totals} error={finance.pricing_error} bold withoutPlan showRealisedTotal />
          {canEdit && <nldd-cell />}
        </nldd-table-row>
      </nldd-table>
    </>
  );
}

interface BudgetSheetProps {
  assignment: AssignmentDetail;
  /** Actions of the part that stand in the bar, next to the choice of a year. */
  actions: readonly ActionBarAction[];
  /** For who may change a line: its row opens the sheet. */
  onOpenLine: (line: BudgetLine) => void;
}

/**
 * After the agreement: what state the money is in, as of when, where it
 * deviates, and how it runs over time. Every number comes from the service.
 */
export function BudgetSheet({ assignment, actions, onOpenLine }: BudgetSheetProps) {
  const [year, setYear] = useState(WHOLE_PERIOD);
  const query = useQuery({
    queryKey: financeKeys.assignment(assignment.id, year),
    queryFn: () => fetchAssignmentFinance(assignment.id, year),
  });
  const budget = useQuery({
    queryKey: assignmentKeys.budget(assignment.id),
    queryFn: () => fetchBudget(assignment.id),
  });
  const frame = useAssignmentFrame();
  // The report row comes with the end of the work; before that the way to it is here.
  const reportLink =
    assignment.permissions.read_financial && !frame?.parts.parts.some((row) => row.key === 'report');
  const years = yearChoices(assignment);
  const finance = query.data;
  const period = periodLabel(year);
  const agreement = finance ? agreementText(finance.key_figures, year) : null;

  return (
    <>
      <ActionBar
        label="Begroting: jaar en looptijd"
        filters={
          years.length > 0
            ? [
                {
                  label: YEAR_FILTER_LABEL,
                  value: year,
                  onChange: setYear,
                  options: years,
                  width: '180px',
                },
              ]
            : []
        }
        actions={actions}
      />
      {(query.isPending || budget.isPending) && <Loading />}
      {query.isError && <LoadError error={query.error} retry={() => void query.refetch()} />}
      {/* The saved lines decide the columns and the names: the table waits, so it does not jump. */}
      {finance && !budget.isPending && (
        <Stack gap="section">
          <Stack gap="related">
            <nldd-text>
              <p>{standText(assignment, year, finance)}</p>
            </nldd-text>
            <BudgetNotices
              budget={budget.data}
              parent={{ start: assignment.start_date, end: assignment.end_date }}
            />
            {finance.lines.length === 0 ? (
              <EmptyNotice text="Deze opdracht heeft nog geen begrotingsregels" />
            ) : (
              <StandTable
                assignment={assignment}
                finance={finance}
                period={period}
                saved={budget.data?.lines ?? []}
                canEdit={budget.data?.can_edit ?? false}
                onOpenLine={onOpenLine}
              />
            )}
            {agreement && <Quiet>{agreement}</Quiet>}
          </Stack>
          <Attention finance={finance} />
          <LineSupport finance={finance} />
          <MonthlyEffort finance={finance} period={period} year={year} />
          {reportLink && (
            <RouterLinks>
              <div>
                <nldd-link
                  size="sm"
                  href={assignmentPartPath(assignment.id, 'report')}
                  text="Rapport van deze opdracht"
                />
              </div>
            </RouterLinks>
          )}
        </Stack>
      )}
    </>
  );
}
