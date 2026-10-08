import { useNavigate } from 'react-router-dom';
import { PATHS } from '@/paths';
import { ActionBar } from '@/ui/ActionBar';
import { OpenCell, OpenRow, ROW_ACTIONS_COLUMN, RowActions } from '@/ui/RowActions';
import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { RolePicker } from '@/features/roles';
import { formatDate, formatEuro, formatFte, formatPeriod } from '@/lib/format';
import {
  addBudgetLine,
  assignmentKeys,
  deleteBudgetLine,
  deriveBudgetLine,
  fetchAssignment,
  fetchBudget,
  fetchPersonOptions,
  previewBudgetLine,
  updateAssignment,
  type AssignmentDetail,
  updateBudgetLine,
  type Budget,
  type BudgetLine,
  type BudgetLineInput,
} from './api';
import {
  effectivePeriod,
  hasOwnPeriod,
  checkLine,
  intendedText,
  lineForm,
  lineInput,
  previewInput,
  type LineField,
  type LineForm,
  type ParentPeriod,
} from './budgetForm';
import { PeriodChoice } from './PeriodChoice';
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
  assignment,
  open,
  session,
  onClose,
}: {
  assignmentId: string;
  line?: BudgetLine;
  /** The assignment: its period is what a line follows by default. */
  assignment?: AssignmentDetail;
  open: boolean;
  /** Changes each time the sheet is opened, so the form starts fresh. */
  session: number;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const parent = { start: assignment?.start_date, end: assignment?.end_date };
  const [form, setForm] = useState<LineForm>(() => lineForm(line, parent));
  const [problem, setProblem] = useState<string | null>(null);
  // What is wrong, said at the field it is about; only after a submit.
  const [fieldProblem, setFieldProblem] = useState<ReturnType<typeof checkLine>>(null);
  const at = (field: LineField) => (fieldProblem?.field === field ? fieldProblem.message : '');
  // The person whose implications still have to be filled in; empty for none.
  const [applyFor, setApplyFor] = useState('');
  const [seenSession, setSeenSession] = useState(session);
  if (seenSession !== session) {
    setSeenSession(session);
    setForm(lineForm(line, parent));
    setProblem(null);
    setFieldProblem(null);
    setApplyFor('');
  }
  const set = (patch: Partial<LineForm>) => {
    setFieldProblem(null);
    setForm((current) => ({ ...current, ...patch }));
  };

  // Scales and rates are per year: those of the year the line starts in, and
  // this year until a start date is entered.
  const rates = useRateCards(open);
  const period = effectivePeriod(form, parent);
  const rateYear = /^\d{4}/.test(period.start)
    ? Number(period.start.slice(0, 4))
    : new Date().getFullYear();
  const endYear = /^\d{4}/.test(period.end) ? Number(period.end.slice(0, 4)) : rateYear;
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
    queryKey: ['budget-derive', assignmentId, form.personId, period.start, period.end, fteValue],
    queryFn: () =>
      deriveBudgetLine(assignmentId, {
        intended_person_id: form.personId,
        ...(period.start ? { start_date: period.start } : {}),
        ...(period.end ? { end_date: period.end } : {}),
        ...(fteValue !== null && Number(fteValue) > 0 ? { fte: fteValue } : {}),
      }),
    enabled: open && form.personId !== '',
    retry: false,
    // Keep the last answer on screen while the period or size is being typed.
    placeholderData: keepPreviousData,
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
      // A proposed period only counts when the assignment has none to follow.
      ...(derivation.period_proposed &&
      derivation.start_date &&
      derivation.end_date &&
      !current.startDate &&
      !current.endDate &&
      !(parent.start && parent.end)
        ? { ownPeriod: true, startDate: derivation.start_date, endDate: derivation.end_date }
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
    const wrong = checkLine(form);
    setFieldProblem(wrong);
    setProblem(null);
    if (wrong) return;
    const input = lineInput(form, !line, line);
    if (typeof input === 'string') {
      setProblem(input);
      return;
    }
    save.mutate(input);
  };

  // "Schaal 12 en 13 (categorie C), € 15.000 per maand", for who may see it.
  const impliedText = impliedCategory ? categoryOptionText(card, impliedCategory) : '';
  // The server's own sentence when it sends one; never a raw condition.
  const resultTitle = derivation?.rate_summary ?? impliedText;
  // The first sentence is about the role; with a role chosen it has nothing to add.
  const resultLines = (derivation?.summary ?? []).slice(form.role ? 1 : 0);
  const roleChoices = form.role ? [] : (derivation?.role_alternatives ?? []).slice(0, 5);
  // A proposal stays marked as one for as long as the user leaves it.
  const proposal = (applies: boolean, source: string | null | undefined) =>
    applies ? `Voorstel${source ? `: ${source}` : ' op basis van de beoogde persoon'}` : '';
  const proposed = {
    role: proposal(!!derivation?.role && form.role === derivation.role, derivation?.role_source_text),
    fte: proposal(
      !!derivation?.fte && form.fte === decimalToInput(derivation.fte),
      derivation?.fte_source_text,
    ),
    period: proposal(
      !!derivation?.period_proposed &&
        !!derivation.start_date &&
        form.ownPeriod &&
        form.startDate === derivation.start_date &&
        form.endDate === (derivation.end_date ?? ''),
      derivation?.period_source_text,
    ),
  };
  // Next to the person when one is chosen, so cause and effect are adjacent;
  // otherwise after the period, where a user expects to choose it.
  const scaleField = (
    <>
          <SelectInput
        label="Schaal en tarief"
        hint={
          at('category') ||
          (followsPerson
            ? `Volgt uit de beoogde persoon. Tarievenkaart van ${rateYear}.`
            : `Volgens de tarievenkaart van ${rateYear}.`)
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
      title={line ? `${lineName(line)} bewerken` : 'Nieuwe begrotingsregel'}
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
          <RolePicker
            label="Rol"
            value={form.role || null}
            onChange={(role) => set({ role: role?.name ?? '' })}
            {...(at('role') || proposed.role ? { supportingLabel: at('role') || proposed.role } : {})}
            invalid={at('role') !== ''}
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
          {form.personId && derivation && (resultTitle || resultLines.length > 0) && (
            // What follows from the person, right where the choice was made.
            <nldd-banner
              variant="accent"
              size="sm"
              text={resultTitle || 'Voorstel op basis van de beoogde persoon'}
              {...(resultLines.length > 0 ? { 'supporting-text': resultLines.join(' ') } : {})}
            />
          )}
          {form.personId && roleChoices.length > 0 && (
            <nldd-button-group>
              {roleChoices.map((choice) => (
                <Button
                  key={choice.role}
                  text={choice.role}
                  size="sm"
                  accessibleLabel={`Kies de rol ${choice.role}`}
                  onClick={() => set({ role: choice.role })}
                />
              ))}
            </nldd-button-group>
          )}
          <TextInput
            label="Omvang in FTE"
            hint={at('fte') || proposed.fte || 'Bijvoorbeeld 0,8'}
            invalid={at('fte') !== ''}
            keyboard="decimal"
            value={form.fte}
            onChange={(fte) => set({ fte })}
            required
          />
          <PeriodChoice
            parent="de opdracht"
            parentStart={parent.start}
            parentEnd={parent.end}
            own={form.ownPeriod}
            onOwn={(ownPeriod) => set({ ownPeriod })}
            startDate={form.startDate}
            endDate={form.endDate}
            onChange={set}
            {...(at('period') || proposed.period ? { hint: at('period') || proposed.period } : {})}
            whenMissing={
              assignment?.permissions.edit_basic ? (
                <AssignmentPeriodStep assignmentId={assignmentId} />
              ) : undefined
            }
          />
          {scaleField}
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
          <TextInput
            label="Omschrijving"
            hint="Wat deze regel onderscheidt van een andere met dezelfde rol, bijvoorbeeld: #2, vanaf Q2."
            value={form.description}
            onChange={(description) => set({ description })}
            optional
          />
        </>
      ) : (
        <>
          <TextInput
            label="Omschrijving"
            {...(at('description') ? { hint: at('description'), invalid: true } : {})}
            value={form.description}
            onChange={(description) => set({ description })}
            required
          />
          <TextInput
            label="Bedrag"
            hint={at('amount') || "In euro's"}
            invalid={at('amount') !== ''}
            keyboard="decimal"
            value={form.amount}
            onChange={(amount) => set({ amount })}
            required
          />
          <TextInput
            label="Jaar"
            {...(at('year') ? { hint: at('year'), invalid: true } : {})}
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

/** A personnel line is named by its role when it has no description of its own. */
const lineName = (line: BudgetLine) => line.description || line.role || 'Begrotingsregel';

/** Sets the assignment's period from inside the sheet, so the user need not leave it. */
function AssignmentPeriodStep({ assignmentId }: { assignmentId: string }) {
  const queryClient = useQueryClient();
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const save = useMutation({
    mutationFn: () => updateAssignment(assignmentId, { start_date: start, end_date: end }),
    onSuccess: (saved) => {
      queryClient.setQueryData(assignmentKeys.detail(assignmentId), saved);
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.budget(assignmentId) });
    },
  });
  return (
    <nldd-container gap="8">
      <nldd-container layout="grid" column-count={2} gap="12">
        <DateInput label="Begin van de opdracht" value={start} onChange={setStart} />
        <DateInput label="Einde van de opdracht" value={end} onChange={setEnd} />
      </nldd-container>
      {save.isError && (
        <nldd-banner variant="critical" size="sm" text={errorMessage(save.error)} />
      )}
      <nldd-container layout="row">
        <Button
          text="Bewaar de looptijd van de opdracht"
          disabled={!start || !end || end < start}
          loading={save.isPending}
          onClick={() => save.mutate()}
        />
      </nldd-container>
    </nldd-container>
  );
}

const lower = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

function lineSummary(line: BudgetLine, name: CategoryNamer, parent?: ParentPeriod): string {
  if (line.kind === 'fixed') return line.year ? `Vast bedrag, ${line.year}` : 'Vast bedrag';
  const parts = [
    line.fte ? `${formatFte(line.fte)} FTE` : '',
    line.rate_category
      ? name(line.rate_category, line.start_date ? Number(line.start_date.slice(0, 4)) : undefined)
      : '',
    // Following the assignment is the normal case; only a deviation is said.
    !parent || hasOwnPeriod(line, parent)
      ? `afwijkende periode: ${formatPeriod(line.start_date, line.end_date)}`
      : '',
  ];
  return parts.filter(Boolean).join(', ');
}

/** The budget lines of an assignment, with the computed amounts and a subtotal per year. */
export function BudgetEditor({ assignmentId }: { assignmentId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
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

  // The assignment's period prices every line that follows it.
  const assignment = useQuery({
    queryKey: assignmentKeys.detail(assignmentId),
    queryFn: () => fetchAssignment(assignmentId),
    retry: false,
  });
  const parent = assignment.data
    ? { start: assignment.data.start_date, end: assignment.data.end_date }
    : undefined;
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
      {budget?.period_missing && budget.period_message && (
        <nldd-banner variant="neutral" size="sm" text={budget.period_message} />
      )}
      {budget?.pricing_error && (
        <nldd-banner
          variant="warning"
          size="sm"
          text="Niet alle regels konden worden berekend."
          supporting-text={budget.pricing_error}
        />
      )}
      {canEdit && (
        <ActionBar
          label="Begroting"
          actions={[{ text: 'Nieuwe begrotingsregel', primary: true, onClick: () => openSheet() }]}
        />
      )}
      {budget && lines.length === 0 && (
        <EmptyNotice text="Deze opdracht heeft nog geen begrotingsregels" />
      )}
      {lines.length > 0 && (
        <nldd-table
          accessible-label="Begrotingsregels"
          columns={`minmax(240px,2fr)${showMoney ? ' 150px' : ''}${canEdit ? ` ${ROW_ACTIONS_COLUMN}` : ''}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Regel" />
            {showMoney && <nldd-text-cell text="Begroot" horizontal-alignment="right" />}
            {canEdit && <nldd-text-cell />}
          </nldd-table-row>
          {lines.map((line) => (
            <OpenRow key={line.id} {...(canEdit ? { onOpen: () => openSheet(line) } : {})}>
              <OpenCell
                text={lineName(line)}
                supportingText={line.pricing_error ?? lineSummary(line, rates.name, parent)}
                {...(canEdit
                  ? { onOpen: () => openSheet(line), accessibleLabel: `Bewerk ${lineName(line)}` }
                  : {})}
              >
                {intendedText(line) && <nldd-tag size="sm" text={intendedText(line)} />}
              </OpenCell>
              {showMoney && (
                <nldd-text-cell
                  text={line.budgeted_cents == null ? 'Niet berekend' : formatEuro(line.budgeted_cents)}
                  horizontal-alignment="right"
                />
              )}
              {canEdit && (
                <RowActions
                  name={lineName(line)}
                  actions={[
                    ...(line.kind === 'personnel'
                      ? [
                          {
                            text: 'Bekijk inzet',
                            onSelect: () => navigate(`${PATHS.allocations}?opdracht=${assignmentId}`),
                          },
                        ]
                      : []),
                    {
                      text: 'Verwijder',
                      destructive: true,
                      confirm: {
                        text: `${lineName(line)} verwijderen?`,
                        supportingText: line.intended_person_name
                          ? `De reservering van ${line.intended_person_name} vervalt ook. Een regel met inzet kan niet weg; haal dan eerst de inzet weg.`
                          : 'Een regel met inzet kan niet weg; haal dan eerst de inzet weg.',
                        confirmText: 'Verwijder',
                      },
                      onSelect: () => remove.mutate(line.id),
                    },
                  ]}
                />
              )}
            </OpenRow>
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
        assignment={assignment.data}
        open={sheet.open}
        onClose={() => setSheet((current) => ({ ...current, open: false }))}
      />
    </nldd-container>
  );
}
