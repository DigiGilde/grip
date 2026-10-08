import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import {
  Button,
  EmptyNotice,
  ErrorNotice,
  InlineSelect,
  Loading,
  SectionHeading,
} from '@/features/assignments/ui';
import { YearFilter } from '@/features/overview/YearFilter';
import { currentYearChoice, periodLabel } from '@/features/overview/years';
import { useInstance } from '@/layout/useInstance';
import { formatEuro, formatPercent, formatPeriod } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { allocationKeys, deleteAllocation, fetchAllocations, type Allocation } from './api';
import { AllocationSheet } from './AllocationSheet';
import { UnfilledRoles } from './UnfilledRoles';
import { groupAllocations, mismatchText, type AllocationGroup, type Grouping } from './grouping';

const GROUPINGS = [
  { value: 'person', label: 'Per persoon' },
  { value: 'line', label: 'Per begrotingsregel' },
];

function GroupTable({
  group,
  grouping,
  onEdit,
  onDelete,
  deleting,
}: {
  group: AllocationGroup;
  grouping: Grouping;
  onEdit: (item: Allocation) => void;
  onDelete: (item: Allocation) => void;
  deleting: string | undefined;
}) {
  const showTime = group.items.some((item) => item.fte_pct !== undefined);
  const showAmount = group.items.some((item) => 'amount_cents' in item);
  const showActions = group.items.some((item) => item.can_edit);
  const first = grouping === 'person' ? 'Opdracht en regel' : 'Persoon';
  return (
    <nldd-container gap="8">
      <SectionHeading text={group.subtitle ? `${group.title}, ${group.subtitle}` : group.title} />
      <nldd-table
        accessible-label={`Inzet: ${group.title}`}
        columns={`minmax(220px,2fr)${showTime ? ' minmax(200px,1.5fr) 100px' : ''}${showAmount ? ' 140px' : ''}${showActions ? ' 220px' : ''}`}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text={first} />
          {showTime && <nldd-text-cell text="Periode" />}
          {showTime && <nldd-text-cell text="Inzet" horizontal-alignment="right" />}
          {showAmount && <nldd-text-cell text="Bedrag" horizontal-alignment="right" />}
          {showActions && <nldd-text-cell text="Acties" />}
        </nldd-table-row>
        {group.items.map((item) => {
          const warning = mismatchText(item);
          const name =
            grouping === 'person'
              ? [item.assignment_name, item.budget_line_description].filter(Boolean).join(': ') ||
                'Opdracht'
              : item.person_name;
          return (
            <nldd-table-row key={item.id}>
              <nldd-text-cell text={name} {...(warning ? { 'supporting-text': warning } : {})} />
              {showTime && <nldd-text-cell text={formatPeriod(item.start_date, item.end_date)} />}
              {showTime && (
                <nldd-text-cell text={formatPercent(item.fte_pct)} horizontal-alignment="right" />
              )}
              {showAmount && (
                <nldd-text-cell
                  text={
                    'amount_cents' in item
                      ? item.amount_cents == null
                        ? 'Niet berekend'
                        : formatEuro(item.amount_cents)
                      : ''
                  }
                  {...(item.pricing_error ? { 'supporting-text': item.pricing_error } : {})}
                  horizontal-alignment="right"
                />
              )}
              {showActions && (
                <nldd-cell>
                  {item.can_edit && (
                    <nldd-button-group>
                      <Button
                        text="Bewerk"
                        size="sm"
                        accessibleLabel={`Bewerk de inzet van ${item.person_name}`}
                        onClick={() => onEdit(item)}
                      />
                      <Button
                        text="Verwijder"
                        size="sm"
                        appearance="neutral-transparent"
                        accessibleLabel={`Verwijder de inzet van ${item.person_name}`}
                        loading={deleting === item.id}
                        onClick={() => onDelete(item)}
                      />
                    </nldd-button-group>
                  )}
                </nldd-cell>
              )}
            </nldd-table-row>
          );
        })}
      </nldd-table>
    </nldd-container>
  );
}

/** Inzet per person and per budget line. */
export function AllocationsPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const [year, setYear] = useState(currentYearChoice);
  const [grouping, setGrouping] = useState<Grouping>('person');
  const [sheet, setSheet] = useState<{ open: boolean; session: number; allocation?: Allocation }>({
    open: false,
    session: 0,
  });
  const [problem, setProblem] = useState<string | null>(null);

  const query = useQuery({
    queryKey: allocationKeys.list(year),
    queryFn: () => fetchAllocations(year),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteAllocation(id),
    onSuccess: () => {
      setProblem(null);
      void queryClient.invalidateQueries({ queryKey: allocationKeys.all });
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
    },
    // Removing inzet from a closed month is refused with a clear sentence.
    onError: (error) => setProblem(errorMessage(error)),
  });

  const items = query.data?.items ?? [];
  const groups = groupAllocations(items, grouping);
  const openSheet = (allocation?: Allocation) =>
    setSheet((current) => ({ open: true, session: current.session + 1, allocation }));

  return (
    <nldd-simple-section>
      <PageHeading text="Inzet" instanceName={instance?.name} />
      <nldd-container gap="16">
        <nldd-container layout="row" gap="12">
          <YearFilter value={year} onChange={setYear} />
          <InlineSelect
            label="Groeperen"
            value={grouping}
            onChange={(value) => setGrouping(value === 'line' ? 'line' : 'person')}
            options={GROUPINGS}
            width="220px"
          />
          {query.data?.can_add && (
            <Button text="Nieuwe inzet" appearance="primary" onClick={() => openSheet()} />
          )}
        </nldd-container>
        {query.isPending && <Loading />}
        {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
        {problem && <ErrorNotice message={problem} />}
        {query.isSuccess && items.length === 0 && (
          <EmptyNotice
            text="Er is geen inzet om te tonen"
            supportingText={`Bedragen gaan over ${periodLabel(year)}. Je ziet je eigen inzet en die op opdrachten waar je bij betrokken bent.`}
          />
        )}
        <UnfilledRoles />
        {groups.map((group) => (
          <GroupTable
            key={group.key}
            group={group}
            grouping={grouping}
            onEdit={openSheet}
            onDelete={(item) => remove.mutate(item.id)}
            deleting={remove.isPending ? remove.variables : undefined}
          />
        ))}
      </nldd-container>
      <AllocationSheet
        open={sheet.open}
        session={sheet.session}
        allocation={sheet.allocation}
        onClose={() => setSheet((current) => ({ ...current, open: false }))}
      />
    </nldd-simple-section>
  );
}
