import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { RolePicker } from '@/features/roles';
import { formatDate, formatEuro, formatFte, formatPeriod } from '@/lib/format';
import {
  addBudgetLine,
  assignmentKeys,
  deleteBudgetLine,
  deriveBudgetLine,
  fetchBudget,
  fetchPersonOptions,
  previewBudgetLine,
  updateBudgetLine,
  type Budget,
  type BudgetLine,
  type BudgetLineInput,
} from './api';
import { intendedText, lineForm, lineInput, previewInput, type LineForm } from './budgetForm';
import { decimalToInput, parseDecimal } from './money';
import { RouterLinks } from '@/layout/RouterLinks';
import { LINE_KIND_LABELS, RATE_CATEGORIES } from './labels';
import {
  cardOfYear,
  categoryDiffers,
  categoryOptionText,
  categoryText,
  useRateCards,
  type CategoryNamer,
} from './rateText';
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
  // The person whose implications still have to be filled in; empty for none.
  const [applyFor, setApplyFor] = useState('');
  const [seenSession, setSeenSession] = useState(session);
  if (seenSession !== session) {
    setSeenSession(session);
    setForm(lineForm(line));
    setProblem(null);
    setApplyFor('');
  }
  const set = (patch: Partial<LineForm>) => setForm((current) => ({ ...current, ...patch }));

  // Scales and rates are per year: those of the year the line starts in, and
  // this year until a start date is entered.
  const rates = useRateCards(open);
  const rateYear = /^\d{4}/.test(form.startDate)
    ? Number(form.startDate.slice(0, 4))
    : new Date().getFullYear();
  const endYear = /^\d{4}/.test(form.endDate) ? Number(form.endDate.slice(0, 4)) : rateYear;
  const card = cardOfYear(rates.cards, rateYear);
  const endCard = endYear !== rateYear ? cardOfYear(rates.cards, endYear) : null;

  const people = useQuery({
    queryKey: assignmentKeys.personOptions,
    queryFn: fetchPersonOptions,
    enabled: open && form.kind === 'personnel',
    retry: false,
  });
  // What follows from the intended person, asked again when the period or
  // the size changes. Nothing is saved by asking.
  const fteValue = parseDecimal(form.fte);
  const derived = useQuery({
    queryKey: ['budget-derive', assignmentId, form.personId, form.startDate, form.endDate, fteValue],
    queryFn: () =>
      deriveBudgetLine(assignmentId, {
        intended_person_id: form.personId,
        ...(form.startDate ? { start_date: form.startDate } : {}),
        ...(form.endDate ? { end_date: form.endDate } : {}),
        ...(fteValue !== null && Number(fteValue) > 0 ? { fte: fteValue } : {}),
      }),
    enabled: open && form.personId !== '',
    retry: false,
  });
  const derivation = form.personId ? derived.data : undefined;
  // A newly chosen person fills in what follows from them, once; after that
  // the fields are the user's to change.
  if (applyFor && derivation && derivation.intended_person_id === applyFor) {
    setApplyFor('');
    setForm((current) => ({
      ...current,
      ...(derivation.rate_category ? { category: derivation.rate_category } : {}),
      ...(derivation.role && !current.role ? { role: derivation.role } : {}),
      ...(derivation.fte && !current.fte ? { fte: decimalToInput(derivation.fte) } : {}),
      ...(derivation.period_proposed && !current.startDate && derivation.start_date
        ? { startDate: derivation.start_date }
        : {}),
      ...(derivation.period_proposed && !current.endDate && derivation.end_date
        ? { endDate: derivation.end_date }
        : {}),
    }));
  }
  const impliedCategory = derivation?.rate_category ?? '';
  const followsPerson = impliedCategory !== '' && form.category === impliedCategory;
  const departsFromPerson = impliedCategory !== '' && form.category !== '' && !followsPerson;

  // The outcome of the line as the server prices it, while it is filled in.
  const toPrice = previewInput(form);
  const preview = useQuery({
    queryKey: ['budget-preview', assignmentId, toPrice],
    queryFn: () => previewBudgetLine(assignmentId, toPrice),
    enabled: open,
    retry: false,
  });

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
    const input = lineInput(form, !line, line);
    if (typeof input === 'string') {
      setProblem(input);
      return;
    }
    save.mutate(input);
  };

  // "Schaal 12 en 13 (categorie C), € 15.000 per maand", for who may see it.
  const impliedText = impliedCategory ? categoryOptionText(card, impliedCategory) : '';
  // Next to the person when one is chosen, so cause and effect are adjacent;
  // otherwise after the period, where a user expects to choose it.
  const scaleField = (
    <>
          <SelectInput
        label="Schaal en tarief"
        hint={
          followsPerson
            ? `Volgt uit de beoogde persoon. Tarievenkaart van ${rateYear}.`
            : `Volgens de tarievenkaart van ${rateYear}.`
        }
        value={form.category}
        onChange={(category) => set({ category })}
        placeholder="Kies een schaal"
        options={RATE_CATEGORIES.map((c) => ({ value: c, label: categoryOptionText(card, c) }))}
        required={!form.personId}
      />
      {departsFromPerson && (
        <nldd-banner
          variant="warning"
          size="sm"
          text={`De beoogde persoon declareert in ${lower(categoryText(card, impliedCategory))}`}
          supporting-text="Je kiest een andere schaal dan uit de persoon volgt. De regel wordt begroot met jouw keuze."
        />
      )}
    </>
  );

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
      {form.kind === 'personnel' ? (
        <>
          {/* ROLE PICKER GOES HERE. Replace this text field by the RolePicker of
              features/roles once that folder exists; the role then becomes
              required and the description optional. */}
          <RolePicker
            label="Rol"
            value={form.role || null}
            onChange={(role) => set({ role: role?.name ?? '' })}
          />
          <SelectInput
            label="Beoogde persoon"
            hint="De naam komt niet in de offerte; daar staat alleen de rol."
            optional
            value={form.personId}
            onChange={(personId) => {
              set({ personId });
              setApplyFor(personId);
            }}
            placeholder="Geen beoogde persoon"
            options={(people.data ?? []).map((person) => ({
              value: person.id,
              label: person.starts_on
                ? `${person.name}, start op ${formatDate(person.starts_on)}`
                : person.name,
            }))}
          />
          {derived.isError && form.personId && (
            <nldd-banner variant="critical" size="sm" text={errorMessage(derived.error)} />
          )}
          {form.personId && derivation && (impliedText || derivation.summary) && (
            // What follows from the person, right where the choice was made.
            <nldd-banner
              variant="accent"
              size="sm"
              text={impliedText ? `Volgt uit de beoogde persoon: ${impliedText}` : 'Volgt uit de beoogde persoon'}
              {...(derivation.summary ? { 'supporting-text': derivation.summary } : {})}
            />
          )}
          {form.personId && scaleField}
          <TextInput
            label="Omschrijving"
            hint="Wat deze regel onderscheidt van een andere met dezelfde rol, bijvoorbeeld: #2, vanaf Q2."
            value={form.description}
            onChange={(description) => set({ description })}
            optional
          />
          <TextInput
            label="Omvang in FTE"
            hint="Bijvoorbeeld 0,8"
            keyboard="decimal"
            value={form.fte}
            onChange={(fte) => set({ fte })}
            required
          />
          <nldd-container layout="grid" column-count={2} gap="12">
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
          </nldd-container>
          {!form.personId && scaleField}
          {rates.loaded && !card && (
            <RouterLinks>
              <nldd-banner
                variant="warning"
                size="sm"
                text={`Er is geen actieve tarievenkaart voor ${rateYear}`}
                supporting-text="Zonder tarievenkaart kan deze regel niet worden berekend."
              />
              <nldd-link href="/beheer/tarieven" text="Bekijk de tarievenkaarten" size="md" />
            </RouterLinks>
          )}
          {endCard && form.category && categoryDiffers(card, endCard, form.category) && (
            <nldd-banner
              variant="neutral"
              size="sm"
              text={`In ${endYear} geldt: ${categoryOptionText(endCard, form.category)}`}
              supporting-text="De regel loopt over twee tariefjaren. Elke maand wordt geprijsd met de kaart van haar jaar."
            />
          )}
        </>
      ) : (
        <>
          <TextInput
            label="Omschrijving"
            value={form.description}
            onChange={(description) => set({ description })}
            required
          />
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
      {/* The outcome, priced by the server: never added up in the browser. */}
      {preview.data?.budgeted_cents != null && (
        <nldd-text>
          Begroot voor deze regel: <strong>{formatEuro(preview.data.budgeted_cents)}</strong>
        </nldd-text>
      )}
      {preview.data?.reason && <nldd-text color="secondary">{preview.data.reason}</nldd-text>}
    </FormSheet>
  );
}

const lower = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

function lineSummary(line: BudgetLine, name: CategoryNamer): string {
  if (line.kind === 'fixed') return line.year ? `Vast bedrag, ${line.year}` : 'Vast bedrag';
  const parts = [
    line.role,
    line.fte ? `${formatFte(line.fte)} FTE` : '',
    line.rate_category
      ? name(line.rate_category, line.start_date ? Number(line.start_date.slice(0, 4)) : undefined)
      : '',
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

  const rates = useRateCards();
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
                supporting-text={
                  line.pricing_error ??
                  [lineSummary(line, rates.name), intendedText(line)].filter(Boolean).join('. ')
                }
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
