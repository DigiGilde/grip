import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { decimalToInput, parseDecimal } from '@/features/assignments/money';
import { PeriodChoice } from '@/features/assignments/PeriodChoice';
import { FormSheet, SelectInput, TextInput } from '@/features/assignments/ui';
import { formatFte, formatMonth, formatPeriod } from '@/lib/format';
import { RowMenu } from '@/ui/RowActions';
import {
  addAllocation,
  allocationKeys,
  deleteAllocation,
  fetchAllocationOptions,
  fetchAllocationOptionsOf,
  previewAllocationLoad,
  updateAllocation,
  type Allocation,
  type LineChoice,
} from './api';
import { overLoadText } from './load';

interface Props {
  open: boolean;
  /** Changes each time the sheet is opened, so the form starts fresh. */
  session: number;
  /** The inzet to change; omit to add one. */
  allocation?: Allocation;
  /** What a new inzet starts from, e.g. the person and month picked on the board. */
  preset?: AllocationPreset;
  /**
   * The assignment whose page the sheet is on: only its lines are offered,
   * without its name, and a single line is chosen already.
   */
  assignmentId?: string;
  /** Closed months of the inzet being changed (first days); they cannot change. */
  closedMonths?: readonly string[];
  onClose: () => void;
}

export interface AllocationPreset {
  personId?: string;
  lineId?: string;
  startDate?: string;
  endDate?: string;
}

interface FormState {
  personId: string;
  lineId: string;
  startDate: string;
  endDate: string;
  /** True when the inzet has its own period; otherwise it follows the budget line. */
  ownPeriod: boolean;
  pct: string;
}

const initial = (allocation?: Allocation, preset?: AllocationPreset): FormState => ({
  personId: allocation?.person_id ?? preset?.personId ?? '',
  lineId: allocation?.budget_line_id ?? preset?.lineId ?? '',
  startDate: allocation?.start_date ?? preset?.startDate ?? '',
  endDate: allocation?.end_date ?? preset?.endDate ?? '',
  // A month picked on the board is a period of its own.
  ownPeriod: allocation
    ? allocation.period_source !== 'line'
    : Boolean(preset?.startDate || preset?.endDate),
  pct: decimalToInput(allocation?.fte_pct),
});

function lineLabel(line: LineChoice, withAssignment: boolean): string {
  const demand = [
    line.fte ? `${formatFte(line.fte)} FTE` : '',
    formatPeriod(line.start_date, line.end_date),
  ]
    .filter(Boolean)
    .join(', ');
  const name = withAssignment ? `${line.assignment_name}: ${line.description}` : line.description;
  return `${name}${demand ? ` (${demand})` : ''}`;
}

export function AllocationSheet({
  open,
  session,
  allocation,
  preset,
  assignmentId,
  closedMonths = [],
  onClose,
}: Props) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(() => initial(allocation, preset));
  const [problem, setProblem] = useState<string | null>(null);
  const [seenSession, setSeenSession] = useState(session);
  if (seenSession !== session) {
    setSeenSession(session);
    setForm(initial(allocation, preset));
    setProblem(null);
  }
  const set = (patch: Partial<FormState>) => setForm((current) => ({ ...current, ...patch }));

  const options = useQuery({
    queryKey: assignmentId ? allocationKeys.optionsOf(assignmentId) : allocationKeys.options,
    queryFn: () =>
      assignmentId ? fetchAllocationOptionsOf(assignmentId) : fetchAllocationOptions(),
    enabled: open && !allocation,
  });
  // Also filtered here, so an older server that ignores the context still
  // offers nothing of another assignment.
  const lines = (options.data?.lines ?? []).filter(
    (line) => !assignmentId || line.assignment_id === assignmentId,
  );
  // One role to put someone on: it is chosen already.
  const onlyLine = assignmentId && lines.length === 1 ? lines[0] : undefined;
  if (onlyLine && !allocation && form.lineId === '') {
    setForm((current) => ({ ...current, lineId: onlyLine.budget_line_id }));
  }

  // Inzet runs over the period of its budget line unless it deviates. For an
  // existing inzet that follows, the dates in force are those of the line.
  const chosenLine = lines.find((line) => line.budget_line_id === form.lineId);
  const follows = allocation?.period_source === 'line';
  const lineStart = chosenLine?.start_date ?? (follows ? allocation?.start_date : undefined);
  const lineEnd = chosenLine?.end_date ?? (follows ? allocation?.end_date : undefined);
  const period = form.ownPeriod
    ? { period_source: 'own' as const, start_date: form.startDate, end_date: form.endDate }
    : { period_source: 'line' as const };

  // What the inzet does to the person's load, asked while the form is
  // filled in: planning above 100 percent is allowed, but never unseen.
  const wantedPct = parseDecimal(form.pct);
  const pctValid = wantedPct !== null && Number(wantedPct) > 0 && Number(wantedPct) <= 100;
  const loadInput = {
    ...(allocation
      ? { allocation_id: allocation.id }
      : { budget_line_id: form.lineId, person_id: form.personId }),
    ...period,
    fte_pct: wantedPct ?? '',
  };
  const load = useQuery({
    // A key of its own: refreshing the inzet after a save or a removal must
    // not ask again about an inzet that is gone.
    queryKey: ['allocation-load', loadInput],
    queryFn: () => previewAllocationLoad(loadInput),
    enabled:
      open &&
      pctValid &&
      (Boolean(allocation) || (form.personId !== '' && form.lineId !== '')) &&
      (!form.ownPeriod || (form.startDate !== '' && form.endDate !== '')),
    retry: false,
    placeholderData: keepPreviousData,
  });
  const overLoad = pctValid ? overLoadText(load.data) : null;

  const remove = useMutation({
    mutationFn: () => deleteAllocation((allocation as Allocation).id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: allocationKeys.all });
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
      setProblem(null);
      onClose();
    },
    // The server refuses for a month that is closed, and says so.
    onError: (error) => setProblem(errorMessage(error)),
  });

  const save = useMutation({
    mutationFn: (pct: string) =>
      allocation
        ? updateAllocation(allocation.id, { ...period, fte_pct: pct })
        : addAllocation({
            budget_line_id: form.lineId,
            person_id: form.personId,
            ...period,
            fte_pct: pct,
          }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: allocationKeys.all });
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
      setProblem(null);
      onClose();
    },
    // A closed month comes back as a conflict with a sentence that says
    // which month and what to do; show it as it is.
    onError: (error) => setProblem(errorMessage(error)),
  });

  const submit = () => {
    if (!allocation && (!form.personId || !form.lineId)) {
      setProblem('Kies een persoon en een begrotingsregel.');
      return;
    }
    if (form.ownPeriod && (!form.startDate || !form.endDate)) {
      setProblem('Vul de begin- en einddatum in.');
      return;
    }
    const pct = parseDecimal(form.pct);
    if (pct === null || Number(pct) <= 0 || Number(pct) > 100) {
      setProblem('Het percentage ligt boven 0 en is hoogstens 100.');
      return;
    }
    save.mutate(pct);
  };

  const title = allocation ? `Inzet van ${allocation.person_name} bewerken` : 'Nieuwe inzet';

  return (
    <FormSheet
      open={open}
      title={title}
      submitText={overLoad ? 'Bewaar boven 100%' : 'Bewaar'}
      onSubmit={submit}
      onClose={onClose}
      busy={save.isPending || remove.isPending}
      error={problem ?? (options.isError ? errorMessage(options.error) : null)}
    >
      {!allocation && (
        <>
          <SelectInput
            label="Persoon"
            value={form.personId}
            onChange={(personId) => set({ personId })}
            placeholder="Kies een persoon"
            options={(options.data?.people ?? []).map((p) => ({ value: p.id, label: p.name }))}
            required
          />
          <SelectInput
            label="Begrotingsregel"
            value={form.lineId}
            onChange={(lineId) => set({ lineId })}
            placeholder="Kies een begrotingsregel"
            options={lines.map((line) => ({
              value: line.budget_line_id,
              label: lineLabel(line, !assignmentId),
            }))}
            required
          />
        </>
      )}
      {closedMonths.length > 0 && (
        <nldd-banner
          variant="neutral"
          size="sm"
          text={`Vastgesteld t/m ${formatMonth(closedMonths[closedMonths.length - 1])}`}
          supporting-text="Afgesloten maanden kun je hier niet wijzigen. Heropen de maand bij de maandafsluiting van de opdracht om dat wel te doen."
        />
      )}
      {/* Nothing to follow until a line is chosen. */}
      {(allocation || chosenLine || form.ownPeriod) && (
        <PeriodChoice
          parent="de regel"
          parentStart={lineStart}
          parentEnd={lineEnd}
          own={form.ownPeriod}
          onOwn={(ownPeriod) => set({ ownPeriod })}
          startDate={form.startDate}
          endDate={form.endDate}
          onChange={set}
        />
      )}
      <TextInput
        label="Inzet in procenten"
        hint="Deel van een volledige werkweek, bijvoorbeeld 50"
        keyboard="decimal"
        value={form.pct}
        onChange={(pct) => set({ pct })}
        required
      />
      {overLoad && (
        <nldd-banner
          variant="warning"
          size="sm"
          text={overLoad}
          supporting-text="Dat mag, als je het zo bedoelt. De knop zegt wat je bewaart."
        />
      )}
      {allocation && (
        <div>
          <RowMenu
            name={`de inzet van ${allocation.person_name}`}
            size="md"
            actions={[
              {
                text: 'Verwijder de inzet',
                destructive: true,
                confirm: {
                  text: `De inzet van ${allocation.person_name} verwijderen?`,
                  supportingText:
                    'De inzet verdwijnt uit de planning en uit de prognose. Is de inzet alleen eerder afgelopen, wijzig dan de einddatum.',
                  confirmText: 'Verwijder',
                },
                onSelect: () => remove.mutate(),
              },
            ]}
          />
        </div>
      )}
    </FormSheet>
  );
}
