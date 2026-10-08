import { ReadOnlyNote } from '../ReadOnlyNote';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { AllocationSheet, type AllocationPreset } from '@/features/allocations/AllocationSheet';
import type { Allocation } from '@/features/allocations/api';
import { VACANCY_KEYS, fetchUnfilledRoles, newVacancyPath } from '@/features/vacancies/api';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatMonth } from '@/lib/format';
import { PATHS } from '@/paths';
import { ActionBar } from '@/ui/ActionBar';
import { CellPanel } from '@/ui/timeline/CellPanel';
import { barsInColumn, cellDescription, type TimelineBar, type TimelineRow } from '@/ui/timeline/layout';
import { Timeline } from '@/ui/timeline/Timeline';
import { useRateCards } from '../rateText';
import { useAssignmentShell } from '../shell';
import { fetchAssignmentStaffing, staffingKeys, type RoleStaffing } from '../staffingApi';
import { lastDayOfMonth, staffingRows, staffingSummary, type RoleBarData } from '../staffingModel';
import { assignmentTabPath } from '../paths';
import { ownersText } from '../steps';
import { Button, ErrorNotice, Loading } from '../ui';

interface SheetState {
  open: boolean;
  session: number;
  allocation?: Allocation;
  preset?: AllocationPreset;
  closedMonths?: string[];
}

type Row = TimelineRow<RoleStaffing, RoleBarData>;
type Bar = TimelineBar<RoleBarData>;

/**
 * Per role what is asked (the frame), who fills it (the bars) and what is
 * still open (the dashed stretch). No amounts here at all: a planner and an
 * owner see the same picture, and money has its own tab.
 */
export function StaffingTab() {
  const assignment = useAssignmentShell();
  const assignmentId = assignment?.id ?? '';
  const [sheet, setSheet] = useState<SheetState>({ open: false, session: 0 });
  const [selected, setSelected] = useState<{ row: Row; column: number } | null>(null);
  const rates = useRateCards();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: staffingKeys.assignment(assignmentId),
    queryFn: () => fetchAssignmentStaffing(assignmentId),
    enabled: assignmentId !== '',
  });
  // Whether a vacancy may be opened for a role is the vacancy module's call.
  const vacancyRoles = useQuery({
    queryKey: VACANCY_KEYS.unfilledRoles,
    queryFn: fetchUnfilledRoles,
    enabled: assignmentId !== '',
    retry: false,
  });
  if (!assignment) return null;

  const staffing = query.data;
  const mayOpenVacancy = new Set(
    (Array.isArray(vacancyRoles.data) ? vacancyRoles.data : []).map((role) => role.budget_line_id),
  );
  const canEdit = assignment.permissions.edit_staffing;
  const mayBudget = assignment.permissions.edit_financial;
  const hasRoles = (staffing?.roles.length ?? 0) > 0;
  const hasInzet = (staffing?.roles ?? []).some(
    (role) => role.bars.length > 0 || (role.names ?? []).length > 0,
  );
  const seesTime = staffing ? staffing.roles.some((role) => role.months && role.months.length > 0) : false;
  const groups = staffing
    ? staffingRows(staffing, (role) =>
        !role.fully_staffed && mayOpenVacancy.has(role.budget_line_id)
          ? { href: newVacancyPath(role.budget_line_id), text: 'Open een vacature' }
          : null,
        rates.name,
      )
    : [];
  const months = staffing?.months ?? [];
  const first = months[0];
  const last = months[months.length - 1];

  const openSheet = (state: Omit<SheetState, 'open' | 'session'>) =>
    setSheet((current) => ({ ...state, open: true, session: current.session + 1 }));

  const actOnBar = (bar: Bar, row: Row) => {
    const { bar: person, gap } = bar.data;
    if (gap && row.data.can_fill) {
      // Exactly the stretch that is open.
      const roleEnd = row.data.end_date ?? '';
      const gapEnd = lastDayOfMonth(gap.end);
      openSheet({
        preset: {
          lineId: row.data.budget_line_id,
          startDate: gap.start,
          endDate: roleEnd && roleEnd < gapEnd ? roleEnd : gapEnd,
        },
      });
    } else if (person?.can_edit) {
      openSheet({
        allocation: {
          id: person.allocation_id,
          person_id: person.person_id,
          person_name: person.person_name,
          budget_line_id: person.budget_line_id,
          start_date: person.start_date,
          end_date: person.end_date,
          fte_pct: person.fte_pct,
        },
        closedMonths: person.closed_months,
      });
    }
  };

  const proposeFrom = (row: Row, column: number) => {
    const month = months[column];
    if (month) openSheet({ preset: { lineId: row.data.budget_line_id, startDate: month } });
  };

  const selectedMonth = selected ? months[selected.column] : undefined;

  return (
    <nldd-simple-section>
      <nldd-container gap="16">
        {!canEdit && (
          <ReadOnlyNote
            assignment={assignment}
            what="de bemensing"
            others="een manager of een planner"
          />
        )}
        {canEdit && hasRoles && (
          <ActionBar
            label="Bemensing"
            actions={[{ text: 'Nieuwe inzet', onClick: () => openSheet({}), primary: true }]}
          />
        )}
        {assignment.phase === 'potential' && hasInzet && (
          <nldd-banner
            variant="warning"
            size="sm"
            text="Inzet onder voorbehoud"
            supporting-text="Dit is nog een potentiële opdracht. De inzet hieronder gaat pas in als de opdrachtgever akkoord geeft."
          />
        )}
        {query.isPending && <Loading />}
        {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
        {staffing && !hasRoles && (
          // Nothing to put a person on yet: say what comes first and whose turn it is.
          <nldd-inline-dialog
            text="Deze opdracht heeft nog geen rollen"
            supporting-text={
              mayBudget
                ? 'Rollen komen uit de begroting: maak daar een personeelsregel per rol.'
                : `${ownersText(assignment)} maakt eerst de begroting. Daarna kun je hier mensen inzetten.`
            }
          >
            {mayBudget && (
              <Button
                slot="actions"
                appearance="primary"
                text="Maak de begroting"
                onClick={() => navigate(assignmentTabPath(assignment.id, 'budget'))}
              />
            )}
          </nldd-inline-dialog>
        )}
        {staffing && staffing.roles.length > 0 && !seesTime && (
          // A team member sees who is on the team, not when or how much.
          <nldd-table accessible-label="Wie op welke rol zit" columns="minmax(200px,1fr) minmax(240px,2fr)">
            <nldd-table-row slot="header">
              <nldd-text-cell text="Rol" />
              <nldd-text-cell text="Wie" />
            </nldd-table-row>
            {staffing.roles.map((role) => (
              <nldd-table-row key={role.budget_line_id}>
                <nldd-text-cell text={role.role ?? role.description} />
                <nldd-text-cell text={(role.names ?? []).join(', ') || 'Nog niemand'} />
              </nldd-table-row>
            ))}
          </nldd-table>
        )}
        {staffing && seesTime && first && last && (
          <>
            <RouterLinks>
              <nldd-table
                accessible-label="Hoe de rollen ervoor staan"
                columns="repeat(3, minmax(180px, 1fr))"
              >
                <nldd-table-row slot="header">
                  {staffingSummary(staffing).map((figure) => (
                    <nldd-text-cell key={figure.label} text={figure.label} />
                  ))}
                </nldd-table-row>
                <nldd-table-row>
                  {staffingSummary(staffing).map((figure) => (
                    <nldd-text-cell
                      key={figure.label}
                      text={figure.attention ? `**${figure.value}**` : figure.value}
                      {...(figure.detail ? { 'supporting-text': figure.detail } : {})}
                    />
                  ))}
                </nldd-table-row>
              </nldd-table>
              {(staffing.overbooked_count ?? 0) > 0 && (
                <nldd-link
                  href={`${PATHS.allocations}?opdracht=${assignment.id}`}
                  text="Bekijk deze opdracht op het bord Inzet"
                  size="md"
                />
              )}
              <Timeline
                label={`Bemensing per rol, ${formatMonth(first)} t/m ${formatMonth(last)}`}
                rowHeader="Rol"
                months={months}
                currentMonth={staffing.current_month}
                closedMonths={staffing.closed_months ?? []}
                groups={groups}
                selected={selected ? { rowKey: selected.row.key, column: selected.column } : null}
                onBar={actOnBar}
                onCell={(row, column, source) => {
                  if (source === 'pointer' && row.data.can_fill && barsInColumn(row, column).length === 0) {
                    proposeFrom(row, column);
                    return;
                  }
                  setSelected({ row, column });
                }}
                legend={['demand', 'filled', 'established', 'tentative', 'open', 'over', 'mismatch']}
              />
            </RouterLinks>
            {selected && selectedMonth && (
              <CellPanel
                cellKey={`${selected.row.key}-${selected.column}`}
                title={`${selected.row.label}, ${formatMonth(selectedMonth)}`}
                summary={selected.row.cells[selected.column]?.description ?? cellDescription(selected.row as TimelineRow, selected.column)}
                items={barsInColumn(selected.row, selected.column).map((bar) => {
                  const editable = bar.data.gap ? selected.row.data.can_fill : bar.data.bar?.can_edit;
                  return {
                    key: bar.key,
                    text: bar.description,
                    ...(editable
                      ? {
                          action: {
                            text: bar.data.gap ? 'Vul in' : 'Bewerk',
                            onClick: () => actOnBar(bar, selected.row),
                          },
                        }
                      : {}),
                  };
                })}
                {...(selected.row.data.can_fill
                  ? {
                      action: {
                        text: `Nieuwe inzet vanaf ${formatMonth(selectedMonth)}`,
                        onClick: () => proposeFrom(selected.row, selected.column),
                      },
                    }
                  : {})}
              />
            )}
          </>
        )}
      </nldd-container>
      <AllocationSheet
        open={sheet.open}
        session={sheet.session}
        allocation={sheet.allocation}
        preset={sheet.preset}
        closedMonths={sheet.closedMonths}
        onClose={() => setSheet((current) => ({ ...current, open: false }))}
      />
    </nldd-simple-section>
  );
}
