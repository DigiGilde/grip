import { Page } from '@/ui/layout';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { useRateCards } from '@/features/assignments/rateText';
import { EmptyNotice, ErrorNotice, Loading } from '@/features/assignments/ui';
import { VACANCY_KEYS, fetchUnfilledRoles, newVacancyPath } from '@/features/vacancies/api';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { formatMonth } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import { AllocationSheet, type AllocationPreset } from './AllocationSheet';
import { allocationKeys, fetchAllocationOptions, type Allocation } from './api';
import { boardKeys, fetchBoard, type BoardBar } from './board/api';
import { CellPanel } from '@/ui/timeline/CellPanel';
import { Timeline, type CellRef } from '@/ui/timeline/Timeline';
import {
  barsInColumn,
  buildGroups,
  describeBar,
  describeCell,
  shiftMonth,
  toTimeline,
  type PlacedBar,
  type RowModel,
  type Show,
  type View,
} from './board/model';

const VIEWS = [
  { value: 'person', label: 'Per persoon' },
  { value: 'team', label: 'Per team' },
  { value: 'assignment', label: 'Per opdracht' },
];

const SHOWS = [
  { value: 'all', label: 'Iedereen' },
  { value: 'room', label: 'Alleen met ruimte' },
  { value: 'over', label: 'Alleen boven 100%' },
];

/** How far "eerder" and "later" move the months on screen. */
const STEP_MONTHS = 3;

function toAllocation(bar: BoardBar): Allocation {
  return {
    id: bar.allocation_id,
    person_id: bar.person_id,
    person_name: bar.person_name,
    budget_line_id: bar.budget_line_id,
    start_date: bar.start_date,
    end_date: bar.end_date,
    fte_pct: bar.fte_pct,
  };
}

interface SheetState {
  open: boolean;
  session: number;
  allocation?: Allocation;
  preset?: AllocationPreset;
  closedMonths?: string[];
}

/**
 * Inzet: the planner's board. Who is available when, where someone is
 * double-booked, which roles are open and what ends soon, and from there:
 * put someone on a role, change an inzet, open a vacancy. No amounts.
 */
export function AllocationsPage() {
  const instance = useInstance();
  // Empty means the server's default: three months back, nine ahead.
  const [start, setStart] = useState('');
  // `?opdracht=<id>` opens the board on one assignment, as the Bemensing tab links to it.
  const [searchParams] = useSearchParams();
  const onlyAssignment = searchParams.get('opdracht');
  // `?persoon=<id>` opens it on one person, as a person's page links to it.
  const onlyPerson = searchParams.get('persoon');
  const [view, setView] = useState<View>(onlyAssignment ? 'assignment' : 'person');
  const [show, setShow] = useState<Show>('all');
  const [selected, setSelected] = useState<{ row: RowModel; column: number } | null>(null);
  const [sheet, setSheet] = useState<SheetState>({ open: false, session: 0 });

  const query = useQuery({ queryKey: boardKeys.board(start), queryFn: () => fetchBoard(start) });
  // Which open roles the reader may open a vacancy for is the vacancy
  // module's call; without that list the link is simply not offered.
  const vacancyRoles = useQuery({
    queryKey: VACANCY_KEYS.unfilledRoles,
    queryFn: fetchUnfilledRoles,
    retry: false,
  });
  const mayOpenVacancy = new Set(
    (Array.isArray(vacancyRoles.data) ? vacancyRoles.data : []).map((role) => role.budget_line_id),
  );

  // Names a category by its scales, for the few who get categories at all.
  const rates = useRateCards();
  const board = query.data;
  const months = board?.months ?? [];
  const allGroups = board ? buildGroups(board, view, show) : [];
  const groups =
    view === 'assignment' && onlyAssignment
      ? allGroups.filter((group) => group.key === onlyAssignment)
      : view === 'person' && onlyPerson
        ? allGroups
            .map((group) => ({
              ...group,
              rows: group.rows.filter((row) => row.key === onlyPerson),
            }))
            .filter((group) => group.rows.length > 0)
        : allGroups;
  const rowCount = groups.reduce((count, group) => count + group.rows.length, 0);
  // Adding needs a role to put someone on; without any, the action is not offered.
  const options = useQuery({
    queryKey: allocationKeys.options,
    queryFn: fetchAllocationOptions,
    enabled: board?.can_add === true,
    retry: false,
  });
  const canAdd = (board?.can_add ?? false) && (options.data?.lines.length ?? 0) > 0;

  const openSheet = (state: Omit<SheetState, 'open' | 'session'>) =>
    setSheet((current) => ({ ...state, open: true, session: current.session + 1 }));

  const editBar = (bar: PlacedBar) => {
    if (bar.role) {
      if (bar.role.can_fill) {
        openSheet({
          preset: {
            lineId: bar.role.budget_line_id,
            startDate: bar.role.start_date ?? '',
            endDate: bar.role.end_date ?? '',
          },
        });
      }
      return;
    }
    if (bar.allocation?.can_edit) {
      openSheet({
        allocation: toAllocation(bar.allocation),
        closedMonths: bar.allocation.closed_months,
      });
    }
  };

  const proposeNew = (row: RowModel, column: number) => {
    const month = months[column];
    if (!month) return;
    openSheet({
      preset: {
        ...(row.person ? { personId: row.person.person_id } : {}),
        ...(row.role ? { lineId: row.role.budget_line_id } : {}),
        startDate: month,
      },
    });
  };

  const onCell = (row: RowModel, column: number, source: 'keyboard' | 'pointer') => {
    const here = barsInColumn(row, column);
    // An empty stretch of a row proposes a new inzet starting that month.
    if (here.length === 0 && canAdd && source === 'pointer') {
      proposeNew(row, column);
      return;
    }
    setSelected({ row, column });
  };

  const selectedRef: CellRef | null = selected
    ? { rowKey: selected.row.key, column: selected.column }
    : null;
  const selectedMonth = selected ? months[selected.column] : undefined;
  const selectedBars = selected ? barsInColumn(selected.row, selected.column) : [];
  const first = months[0];
  const last = months[months.length - 1];
  const move = (count: number) => {
    if (!first) return;
    setSelected(null);
    setStart(shiftMonth(first.slice(0, 7), count));
  };

  return (
    <Page title="Inzet" instanceName={instance?.name}>
        <ActionBar
          label="Inzet: weergave en periode"
          filters={[
            {
              label: 'Weergave',
              value: view,
              onChange: (value) => {
                setSelected(null);
                setView(value === 'team' || value === 'assignment' ? value : 'person');
              },
              options: VIEWS,
              width: '190px',
            },
            ...(view === 'assignment'
              ? []
              : [
                  {
                    label: 'Toon',
                    value: show,
                    onChange: (value: string) => {
                      setSelected(null);
                      setShow(value === 'room' || value === 'over' ? value : 'all');
                    },
                    options: SHOWS,
                    width: '210px',
                  },
                ]),
          ]}
          actions={[
            { text: 'Eerdere maanden', onClick: () => move(-STEP_MONTHS) },
            { text: 'Latere maanden', onClick: () => move(STEP_MONTHS) },
            ...(canAdd
              ? [{ text: 'Nieuwe inzet', primary: true, onClick: () => openSheet({}) }]
              : []),
          ]}
        />
        {query.isPending && <Loading />}
        {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
        {board && rowCount === 0 && (
          <EmptyNotice
            text={
              show === 'over'
                ? 'Niemand is boven 100% ingepland'
                : show === 'room'
                  ? 'Niemand heeft ruimte in deze maanden'
                  : 'Er is geen inzet om te tonen'
            }
            supportingText="Je ziet je eigen inzet en die op opdrachten en van mensen waar je over gaat."
          />
        )}
        {board && rowCount > 0 && first && last && (
          <RouterLinks>
            <Timeline
              label={`Inzet van ${formatMonth(first)} t/m ${formatMonth(last)}`}
              rowHeader={view === 'assignment' ? 'Opdracht en rol' : 'Persoon'}
              months={months}
              currentMonth={board.current_month}
              groups={toTimeline(groups, months, board.current_month, (row) =>
                row.role && mayOpenVacancy.has(row.role.budget_line_id)
                  ? { href: newVacancyPath(row.role.budget_line_id), text: 'Open een vacature' }
                  : null,
                rates.name,
              )}
              selected={selectedRef}
              onBar={(bar) => editBar(bar.data)}
              onCell={(row, column, source) => onCell(row.data, column, source)}
              legend={['filled', 'established', 'tentative', 'open', 'unavailable', 'over', 'mismatch']}
            />
          </RouterLinks>
        )}
        {selected && selectedMonth && (
          <CellPanel
            cellKey={`${selected.row.key}-${selected.column}`}
            title={`${selected.row.label}, ${formatMonth(selectedMonth)}`}
            summary={
              describeCell(selected.row, selected.column, selectedMonth, board?.current_month ?? '')
                .split('; ')[0] ?? ''
            }
            items={selectedBars.map((bar) => {
              const editable = bar.role ? bar.role.can_fill : bar.allocation?.can_edit;
              return {
                key: bar.key,
                text: describeBar(bar, rates.name),
                ...(editable
                  ? { action: { text: bar.role ? 'Vul in' : 'Bewerk', onClick: () => editBar(bar) } }
                  : {}),
              };
            })}
            {...(canAdd && selected.row.kind !== 'line'
              ? {
                  action: {
                    text: `Nieuwe inzet vanaf ${formatMonth(selectedMonth)}`,
                    onClick: () => proposeNew(selected.row, selected.column),
                  },
                }
              : {})}
          />
        )}
      <AllocationSheet
        open={sheet.open}
        session={sheet.session}
        allocation={sheet.allocation}
        preset={sheet.preset}
        closedMonths={sheet.closedMonths}
        onClose={() => setSheet((current) => ({ ...current, open: false }))}
      />
    </Page>
  );
}
