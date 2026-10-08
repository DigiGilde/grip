import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { decimalToInput, parseDecimal } from '@/features/assignments/money';
import { DateInput, FormSheet, SelectInput, TextInput } from '@/features/assignments/ui';
import { formatFte, formatPeriod } from '@/lib/format';
import {
  addAllocation,
  allocationKeys,
  fetchAllocationOptions,
  updateAllocation,
  type Allocation,
  type LineChoice,
} from './api';

interface Props {
  open: boolean;
  /** Changes each time the sheet is opened, so the form starts fresh. */
  session: number;
  /** The inzet to change; omit to add one. */
  allocation?: Allocation;
  onClose: () => void;
}

interface FormState {
  personId: string;
  lineId: string;
  startDate: string;
  endDate: string;
  pct: string;
}

const initial = (allocation?: Allocation): FormState => ({
  personId: allocation?.person_id ?? '',
  lineId: allocation?.budget_line_id ?? '',
  startDate: allocation?.start_date ?? '',
  endDate: allocation?.end_date ?? '',
  pct: decimalToInput(allocation?.fte_pct),
});

function lineLabel(line: LineChoice): string {
  const demand = [
    line.fte ? `${formatFte(line.fte)} FTE` : '',
    formatPeriod(line.start_date, line.end_date),
  ]
    .filter(Boolean)
    .join(', ');
  return `${line.assignment_name}: ${line.description}${demand ? ` (${demand})` : ''}`;
}

export function AllocationSheet({ open, session, allocation, onClose }: Props) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(() => initial(allocation));
  const [problem, setProblem] = useState<string | null>(null);
  const [seenSession, setSeenSession] = useState(session);
  if (seenSession !== session) {
    setSeenSession(session);
    setForm(initial(allocation));
    setProblem(null);
  }
  const set = (patch: Partial<FormState>) => setForm((current) => ({ ...current, ...patch }));

  const options = useQuery({
    queryKey: allocationKeys.options,
    queryFn: fetchAllocationOptions,
    enabled: open && !allocation,
  });

  const save = useMutation({
    mutationFn: (pct: string) =>
      allocation
        ? updateAllocation(allocation.id, {
            start_date: form.startDate,
            end_date: form.endDate,
            fte_pct: pct,
          })
        : addAllocation({
            budget_line_id: form.lineId,
            person_id: form.personId,
            start_date: form.startDate,
            end_date: form.endDate,
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
    if (!form.startDate || !form.endDate) {
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

  const title = allocation
    ? `Inzet van ${allocation.person_name} bewerken`
    : 'Nieuwe inzet';

  return (
    <FormSheet
      open={open}
      title={title}
      submitText="Bewaar"
      onSubmit={submit}
      onClose={onClose}
      busy={save.isPending}
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
            options={(options.data?.lines ?? []).map((line) => ({
              value: line.budget_line_id,
              label: lineLabel(line),
            }))}
            required
          />
        </>
      )}
      <DateInput
        label="Begindatum"
        value={form.startDate}
        onChange={(startDate) => set({ startDate })}
        required
      />
      <DateInput
        label="Einddatum"
        value={form.endDate}
        onChange={(endDate) => set({ endDate })}
        required
      />
      <TextInput
        label="Inzet in procenten"
        hint="Deel van een volledige werkweek, bijvoorbeeld 50"
        keyboard="decimal"
        value={form.pct}
        onChange={(pct) => set({ pct })}
        required
      />
    </FormSheet>
  );
}
