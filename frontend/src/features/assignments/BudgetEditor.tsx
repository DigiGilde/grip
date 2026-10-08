import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatEuro, formatFte, formatPeriod } from '@/lib/format';
import {
  addBudgetLine,
  assignmentKeys,
  deleteBudgetLine,
  fetchBudget,
  updateBudgetLine,
  type Budget,
  type BudgetLine,
  type BudgetLineInput,
} from './api';
import { lineForm, lineInput, type LineForm } from './budgetForm';
import { LINE_KIND_LABELS, RATE_CATEGORIES } from './labels';
import {
  Button,
  DateInput,
  EmptyNotice,
  ErrorNotice,
  FormSheet,
  Loading,
  SectionHeading,
  SelectInput,
  TextInput,
} from './ui';

function LineSheet({
  assignmentId,
  line,
  open,
  session,
  onClose,
}: {
  assignmentId: string;
  line?: BudgetLine;
  open: boolean;
  /** Changes each time the sheet is opened, so the form starts fresh. */
  session: number;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<LineForm>(() => lineForm(line));
  const [problem, setProblem] = useState<string | null>(null);
  const [seenSession, setSeenSession] = useState(session);
  if (seenSession !== session) {
    setSeenSession(session);
    setForm(lineForm(line));
    setProblem(null);
  }
  const set = (patch: Partial<LineForm>) => setForm((current) => ({ ...current, ...patch }));

  const save = useMutation({
    mutationFn: (input: BudgetLineInput) =>
      line ? updateBudgetLine(line.id, input) : addBudgetLine(assignmentId, input),
    onSuccess: (budget: Budget) => {
      queryClient.setQueryData(assignmentKeys.budget(assignmentId), budget);
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
      setProblem(null);
      onClose();
    },
    onError: (error) => setProblem(errorMessage(error)),
  });

  const submit = () => {
    const input = lineInput(form, !line);
    if (typeof input === 'string') {
      setProblem(input);
      return;
    }
    save.mutate(input);
  };

  return (
    <FormSheet
      open={open}
      title={line ? `${line.description} bewerken` : 'Nieuwe begrotingsregel'}
      submitText="Bewaar"
      onSubmit={submit}
      onClose={onClose}
      busy={save.isPending}
      error={problem}
    >
      {!line && (
        <SelectInput
          label="Soort regel"
          value={form.kind}
          onChange={(kind) => set({ kind })}
          options={Object.entries(LINE_KIND_LABELS).map(([value, label]) => ({ value, label }))}
        />
      )}
      <TextInput
        label="Omschrijving"
        value={form.description}
        onChange={(description) => set({ description })}
        required
      />
      {form.kind === 'personnel' ? (
        <>
          <TextInput label="Rol" optional value={form.role} onChange={(role) => set({ role })} />
          <TextInput
            label="Omvang in FTE"
            hint="Bijvoorbeeld 0,8"
            keyboard="decimal"
            value={form.fte}
            onChange={(fte) => set({ fte })}
            required
          />
          <SelectInput
            label="Tariefcategorie"
            value={form.category}
            onChange={(category) => set({ category })}
            placeholder="Kies een categorie"
            options={RATE_CATEGORIES.map((c) => ({ value: c, label: `Categorie ${c}` }))}
            required
          />
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
        </>
      ) : (
        <>
          <TextInput
            label="Bedrag"
            hint="In euro's"
            keyboard="decimal"
            value={form.amount}
            onChange={(amount) => set({ amount })}
            required
          />
          <TextInput
            label="Jaar"
            keyboard="numeric"
            value={form.year}
            onChange={(year) => set({ year })}
            required
          />
        </>
      )}
    </FormSheet>
  );
}

function lineSummary(line: BudgetLine): string {
  if (line.kind === 'fixed') return line.year ? `Vast bedrag, ${line.year}` : 'Vast bedrag';
  const parts = [
    line.role,
    line.fte ? `${formatFte(line.fte)} FTE` : '',
    line.rate_category ? `categorie ${line.rate_category}` : '',
    formatPeriod(line.start_date, line.end_date),
  ];
  return parts.filter(Boolean).join(', ');
}

/** The budget lines of an assignment, with the computed amounts and a subtotal per year. */
export function BudgetEditor({ assignmentId }: { assignmentId: string }) {
  const queryClient = useQueryClient();
  const [sheet, setSheet] = useState<{ open: boolean; line?: BudgetLine; key: number }>({
    open: false,
    key: 0,
  });
  const [problem, setProblem] = useState<string | null>(null);
  const query = useQuery({
    queryKey: assignmentKeys.budget(assignmentId),
    queryFn: () => fetchBudget(assignmentId),
  });

  const remove = useMutation({
    mutationFn: (lineId: string) => deleteBudgetLine(lineId),
    onSuccess: (budget) => {
      queryClient.setQueryData(assignmentKeys.budget(assignmentId), budget);
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
      setProblem(null);
    },
    onError: (error) => setProblem(errorMessage(error)),
  });

  const budget = query.data;
  const lines = budget?.lines ?? [];
  const showMoney = budget !== undefined && 'total_budgeted_cents' in budget;
  const canEdit = budget?.can_edit ?? false;
  const subtotals = Object.entries(budget?.subtotals_by_year ?? {});
  const openSheet = (line?: BudgetLine) =>
    setSheet((current) => ({ open: true, line, key: current.key + 1 }));

  return (
    <nldd-container gap="12">
      <SectionHeading text="Begroting" />
      {query.isPending && <Loading />}
      {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
      {problem && <ErrorNotice message={problem} />}
      {budget?.pricing_error && (
        <nldd-banner
          variant="warning"
          size="sm"
          text="Niet alle regels konden worden berekend."
          supporting-text={budget.pricing_error}
        />
      )}
      {canEdit && (
        <div>
          <Button text="Nieuwe begrotingsregel" onClick={() => openSheet()} />
        </div>
      )}
      {budget && lines.length === 0 && (
        <EmptyNotice text="Deze opdracht heeft nog geen begrotingsregels" />
      )}
      {lines.length > 0 && (
        <nldd-table
          accessible-label="Begrotingsregels"
          columns={`minmax(240px,2fr)${showMoney ? ' 150px' : ''}${canEdit ? ' 220px' : ''}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Regel" />
            {showMoney && <nldd-text-cell text="Begroot" horizontal-alignment="right" />}
            {canEdit && <nldd-text-cell text="Acties" />}
          </nldd-table-row>
          {lines.map((line) => (
            <nldd-table-row key={line.id}>
              <nldd-text-cell
                text={line.description}
                supporting-text={line.pricing_error ?? lineSummary(line)}
              />
              {showMoney && (
                <nldd-text-cell
                  text={line.budgeted_cents == null ? 'Niet berekend' : formatEuro(line.budgeted_cents)}
                  horizontal-alignment="right"
                />
              )}
              {canEdit && (
                <nldd-cell>
                  <nldd-button-group>
                    <Button
                      text="Bewerk"
                      size="sm"
                      accessibleLabel={`Bewerk ${line.description}`}
                      onClick={() => openSheet(line)}
                    />
                    <Button
                      text="Verwijder"
                      size="sm"
                      appearance="neutral-transparent"
                      accessibleLabel={`Verwijder ${line.description}`}
                      loading={remove.isPending && remove.variables === line.id}
                      onClick={() => remove.mutate(line.id)}
                    />
                  </nldd-button-group>
                </nldd-cell>
              )}
            </nldd-table-row>
          ))}
          {showMoney &&
            subtotals.map(([year, cents]) => (
              <nldd-table-row key={`year-${year}`}>
                <nldd-text-cell text={`**Subtotaal ${year}**`} />
                <nldd-text-cell text={`**${formatEuro(cents)}**`} horizontal-alignment="right" />
                {canEdit && <nldd-text-cell />}
              </nldd-table-row>
            ))}
          {showMoney && budget?.total_budgeted_cents != null && (
            <nldd-table-row>
              <nldd-text-cell text="**Totaal begroot**" />
              <nldd-text-cell
                text={`**${formatEuro(budget.total_budgeted_cents)}**`}
                horizontal-alignment="right"
              />
              {canEdit && <nldd-text-cell />}
            </nldd-table-row>
          )}
          {showMoney && budget?.quoted_amount_cents != null && (
            <nldd-table-row>
              <nldd-text-cell text="Offertebedrag" />
              <nldd-text-cell
                text={formatEuro(budget.quoted_amount_cents)}
                horizontal-alignment="right"
              />
              {canEdit && <nldd-text-cell />}
            </nldd-table-row>
          )}
        </nldd-table>
      )}
      <LineSheet
        session={sheet.key}
        assignmentId={assignmentId}
        line={sheet.line}
        open={sheet.open}
        onClose={() => setSheet((current) => ({ ...current, open: false }))}
      />
    </nldd-container>
  );
}
