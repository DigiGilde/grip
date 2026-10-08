import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatEuro, formatMonth, formatPercent } from '@/lib/format';
import { Button, DateField, SelectField, TextField } from '@/features/team/ui/controls';
import { centsToEuroInput, eurosToCents, percentInput } from '@/features/team/ui/money';
import { Form, Sheet } from '@/features/team/ui/overlays';
import { EmptyRows } from '@/features/team/ui/states';
import {
  COVERAGE_OPTIONS_KEY,
  KIND_LABELS,
  addInvoiceLine,
  deleteInvoiceLine,
  fetchCoverageOptions,
  removeCoverage,
  setCoverage,
  updateCostItem,
  type CostItem,
  type InvoiceLine,
} from './api';

interface CostItemSheetProps {
  item: CostItem | null;
  onClose: () => void;
}

/** One cost item: its totals, its invoice lines and what covers it. */
export function CostItemSheet({ item, onClose }: CostItemSheetProps) {
  return (
    <Sheet
      open={item !== null}
      title={item?.description ?? 'Kostenpost'}
      onClose={onClose}
      width="720px"
    >
      {item ? <CostItemDetails key={item.id} item={item} /> : null}
    </Sheet>
  );
}

function useSave() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ['costs'] });
    },
    onError: (err) => setError(errorMessage(err)),
  });
  return { run: mutation.mutate, pending: mutation.isPending, error, setError };
}

function CostItemDetails({ item }: { item: CostItem }) {
  return (
    <nldd-container gap="32">
      <Totals item={item} />
      {item.may_edit ? <ItemForm item={item} /> : null}
      <InvoiceLines item={item} />
      <Coverages item={item} />
    </nldd-container>
  );
}

function Totals({ item }: { item: CostItem }) {
  const exceeded = item.covered_cents === null;
  return (
    <nldd-container gap="8">
      {exceeded ? (
        <nldd-banner
          variant="critical"
          text="De dekking komt boven 100 procent uit"
          supporting-text="Pas de percentages aan; tot die tijd is het gedekte bedrag niet te bepalen."
        />
      ) : null}
      <nldd-table accessible-label={`Totalen van ${item.description}`} columns="1fr 160px">
        <nldd-table-row slot="header">
          <nldd-text-cell text="Totaal" />
          <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Begroot" />
          <nldd-text-cell text={formatEuro(item.budgeted_cents)} horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Realisatie" supporting-text="Ontvangen facturen" />
          <nldd-text-cell text={formatEuro(item.actual_cents)} horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Inschatting" supporting-text="Nog verwachte facturen" />
          <nldd-text-cell text={formatEuro(item.estimate_cents)} horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Prognose" supporting-text="Realisatie plus inschatting" />
          <nldd-text-cell text={formatEuro(item.forecast_cents)} horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell
            text="Gedekt"
            supporting-text={`${formatPercent(item.pct_total)} van de prognose`}
          />
          <nldd-text-cell
            text={exceeded ? 'Onbekend' : formatEuro(item.covered_cents)}
            horizontal-alignment="right"
          />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Ongedekt" />
          <nldd-text-cell
            text={exceeded ? 'Onbekend' : formatEuro(item.uncovered_cents)}
            horizontal-alignment="right"
          />
        </nldd-table-row>
      </nldd-table>
    </nldd-container>
  );
}

function ItemForm({ item }: { item: CostItem }) {
  const save = useSave();
  const [description, setDescription] = useState(item.description);
  const [budgeted, setBudgeted] = useState(centsToEuroInput(item.budgeted_cents));
  return (
    <nldd-container gap="8">
      <nldd-title size={4} text="Gegevens" heading-level={2} />
      <Form
        submitText="Bewaar gegevens"
        submitting={save.pending}
        error={save.error}
        onSubmit={() => {
          const cents = eurosToCents(budgeted);
          if (!description.trim() || cents === null || cents < 0) {
            save.setError('Vul een omschrijving en een begroot bedrag in euro in.');
            return;
          }
          save.run(() => updateCostItem(item.id, { description, budgeted_cents: cents }));
        }}
      >
        <TextField label="Omschrijving" value={description} onChange={setDescription} required />
        <TextField
          label="Begroot bedrag"
          supportingLabel="In euro"
          value={budgeted}
          onChange={setBudgeted}
          keyboard="decimal"
          required
        />
      </Form>
    </nldd-container>
  );
}

function lineLabel(line: InvoiceLine): string {
  return line.reference ?? line.description ?? KIND_LABELS[line.kind];
}

function InvoiceLines({ item }: { item: CostItem }) {
  const save = useSave();
  const [kind, setKind] = useState<InvoiceLine['kind']>('actual');
  const [amount, setAmount] = useState('');
  const [reference, setReference] = useState('');
  const [description, setDescription] = useState('');
  const [period, setPeriod] = useState('');
  return (
    <nldd-container gap="8">
      <nldd-title
        size={4}
        text="Factuurregels"
        heading-level={2}
        supporting-text="Ontvangen facturen (realisatie) en wat nog wordt verwacht (inschatting)"
      />
      <nldd-table
        accessible-label={`Factuurregels van ${item.description}`}
        columns={
          item.may_edit
            ? 'minmax(160px,2fr) 110px minmax(110px,1fr) 120px 110px'
            : 'minmax(160px,2fr) 110px minmax(110px,1fr) 120px'
        }
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Kenmerk" />
          <nldd-text-cell text="Soort" />
          <nldd-text-cell text="Periode" />
          <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
          {item.may_edit ? <nldd-text-cell text="Actie" /> : null}
        </nldd-table-row>
        {item.invoice_lines.map((line) => (
          <nldd-table-row key={line.id}>
            <nldd-text-cell
              text={lineLabel(line)}
              {...(line.reference && line.description
                ? { 'supporting-text': line.description }
                : {})}
            />
            <nldd-text-cell text={KIND_LABELS[line.kind]} />
            <nldd-text-cell text={line.period ? formatMonth(line.period) : 'Geen periode'} />
            <nldd-text-cell text={formatEuro(line.amount_cents)} horizontal-alignment="right" />
            {item.may_edit ? (
              <nldd-cell>
                <Button
                  size="sm"
                  text="Verwijder"
                  accessibleLabel={`Verwijder factuurregel ${lineLabel(line)}`}
                  disabled={save.pending}
                  onClick={() => save.run(() => deleteInvoiceLine(item.id, line.id))}
                />
              </nldd-cell>
            ) : null}
          </nldd-table-row>
        ))}
        <EmptyRows text="Er zijn nog geen factuurregels" />
      </nldd-table>
      {item.may_edit ? (
        <Form
          submitText="Voeg factuurregel toe"
          submitting={save.pending}
          error={save.error}
          onSubmit={() => {
            const cents = eurosToCents(amount);
            if (cents === null) {
              save.setError('Vul een bedrag in euro in.');
              return;
            }
            save.run(async () => {
              await addInvoiceLine(item.id, {
                kind,
                amount_cents: cents,
                reference: reference || null,
                description: description || null,
                period: period || null,
              });
              setAmount('');
              setReference('');
              setDescription('');
            });
          }}
        >
          <SelectField
            label="Soort"
            value={kind}
            onChange={(value) => setKind(value === 'estimate' ? 'estimate' : 'actual')}
            options={[
              { value: 'actual', label: KIND_LABELS.actual },
              { value: 'estimate', label: KIND_LABELS.estimate },
            ]}
          />
          <TextField
            label="Bedrag"
            supportingLabel="In euro"
            value={amount}
            onChange={setAmount}
            keyboard="decimal"
            required
          />
          <DateField
            label="Periode"
            supportingLabel="Een dag in de maand waar het bedrag bij hoort"
            optional
            value={period}
            onChange={setPeriod}
          />
          <TextField label="Kenmerk" optional value={reference} onChange={setReference} />
          <TextField label="Omschrijving" optional value={description} onChange={setDescription} />
        </Form>
      ) : null}
    </nldd-container>
  );
}

function Coverages({ item }: { item: CostItem }) {
  const save = useSave();
  const options = useQuery({ queryKey: COVERAGE_OPTIONS_KEY, queryFn: fetchCoverageOptions });
  const lines = options.data?.items ?? [];
  const [lineId, setLineId] = useState('');
  const [pct, setPct] = useState('');
  const hidden = Number(item.hidden_coverage_pct) > 0;
  const anyEditable = item.coverages.some((c) => c.may_edit);
  return (
    <nldd-container gap="8">
      <nldd-title
        size={4}
        text="Dekking"
        heading-level={2}
        supporting-text="Welke begrotingsregel welk deel van de prognose draagt"
      />
      <nldd-table
        accessible-label={`Dekking van ${item.description}`}
        columns={
          anyEditable ? 'minmax(180px,2fr) 90px 120px 110px' : 'minmax(180px,2fr) 90px 120px'
        }
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Begrotingsregel" />
          <nldd-text-cell text="Deel" horizontal-alignment="right" />
          <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
          {anyEditable ? <nldd-text-cell text="Actie" /> : null}
        </nldd-table-row>
        {item.coverages.map((coverage) => (
          <nldd-table-row key={coverage.budget_line_id}>
            <nldd-text-cell
              text={coverage.budget_line_description}
              supporting-text={coverage.assignment_name}
            />
            <nldd-text-cell text={formatPercent(coverage.pct)} horizontal-alignment="right" />
            <nldd-text-cell text={formatEuro(coverage.amount_cents)} horizontal-alignment="right" />
            {anyEditable ? (
              <nldd-cell>
                {coverage.may_edit ? (
                  <Button
                    size="sm"
                    text="Verwijder"
                    accessibleLabel={`Verwijder de dekking door ${coverage.budget_line_description}, ${coverage.assignment_name}`}
                    disabled={save.pending}
                    onClick={() => save.run(() => removeCoverage(item.id, coverage.budget_line_id))}
                  />
                ) : null}
              </nldd-cell>
            ) : null}
          </nldd-table-row>
        ))}
        <EmptyRows text="Nog geen begrotingsregel dekt deze kostenpost" />
      </nldd-table>
      {hidden ? (
        <nldd-text-cell
          size="sm"
          color="secondary"
          text={`Daarnaast dekken opdrachten die je niet kunt inzien ${formatPercent(item.hidden_coverage_pct)}.`}
        />
      ) : null}
      {lines.length > 0 ? (
        <Form
          submitText="Leg dekking vast"
          submitting={save.pending}
          error={save.error}
          onSubmit={() => {
            const value = percentInput(pct);
            if (!lineId || value === null || Number(value) <= 0 || Number(value) > 100) {
              save.setError(
                'Kies een begrotingsregel en vul een percentage boven 0 tot en met 100 in.',
              );
              return;
            }
            save.run(async () => {
              await setCoverage(item.id, lineId, value);
              setPct('');
            });
          }}
        >
          <SelectField
            label="Begrotingsregel"
            supportingLabel="Van een opdracht die je beheert; een bestaande dekking wordt vervangen"
            value={lineId}
            onChange={setLineId}
            emptyLabel="Kies een begrotingsregel"
            options={lines.map((line) => ({
              value: line.budget_line_id,
              label: line.description,
              group: line.assignment_name,
            }))}
          />
          <TextField
            label="Deel van de prognose"
            supportingLabel="Percentage"
            value={pct}
            onChange={setPct}
            keyboard="decimal"
            required
          />
        </Form>
      ) : null}
    </nldd-container>
  );
}
