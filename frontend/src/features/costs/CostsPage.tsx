import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatEuro, formatPercent } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { Button, SelectField, TextField } from '@/features/team/ui/controls';
import { eurosToCents } from '@/features/team/ui/money';
import { Form, Sheet } from '@/features/team/ui/overlays';
import { EmptyRows, QueryState } from '@/features/team/ui/states';
import { costsKey, createCostItem, fetchCostItems, type CostItem } from './api';
import { CostItemSheet } from './CostItemSheet';

function yearOptions(current: number) {
  return [current - 1, current, current + 1].map((year) => ({
    value: String(year),
    label: String(year),
  }));
}

/** Covered and uncovered are unknown while the shares add up to more than 100. */
function covered(item: CostItem, field: 'covered_cents' | 'uncovered_cents'): string {
  const value = item[field];
  return value === null ? 'Onbekend' : formatEuro(value);
}

/** External costs: what they are forecast to be and which budget lines cover them. */
export function CostsPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState<number | null>(null);
  const query = useQuery({ queryKey: costsKey(year), queryFn: () => fetchCostItems(year) });
  const items = query.data?.items ?? [];
  const mayCreate = query.data?.may_create ?? false;

  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const opened = items.find((item) => item.id === openId) ?? null;

  return (
    <>
      <nldd-simple-section>
        <PageHeading text="Kosten en facturen" instanceName={instance?.name} />
        <nldd-container gap="16">
          <nldd-container layout="wrap" gap="16" vertical-alignment="bottom">
            <SelectField
              width="280px"
              label="Jaar"
              supportingLabel="Telt de factuurregels van dat jaar"
              value={year === null ? '' : String(year)}
              onChange={(value) => setYear(value ? Number(value) : null)}
              emptyLabel="Hele looptijd"
              options={yearOptions(thisYear)}
            />
            {mayCreate ? (
              <Button text="Kostenpost toevoegen" onClick={() => setAdding(true)} />
            ) : null}
          </nldd-container>

          <QueryState query={query}>
            <nldd-table
              accessible-label="Kostenposten"
              columns="minmax(200px,2fr) repeat(4, minmax(110px,1fr)) 90px 110px"
            >
              <nldd-table-row slot="header">
                <nldd-text-cell text="Omschrijving" />
                <nldd-text-cell text="Begroot" horizontal-alignment="right" />
                <nldd-text-cell text="Prognose" horizontal-alignment="right" />
                <nldd-text-cell text="Gedekt" horizontal-alignment="right" />
                <nldd-text-cell text="Ongedekt" horizontal-alignment="right" />
                <nldd-text-cell text="Dekking" horizontal-alignment="right" />
                <nldd-text-cell text="Actie" />
              </nldd-table-row>
              {items.map((item) => (
                <nldd-table-row key={item.id}>
                  <nldd-text-cell
                    text={item.description}
                    supporting-text={`${item.invoice_lines.length} factuurregels`}
                  />
                  <nldd-text-cell
                    text={formatEuro(item.budgeted_cents)}
                    horizontal-alignment="right"
                  />
                  <nldd-text-cell
                    text={formatEuro(item.forecast_cents)}
                    horizontal-alignment="right"
                    {...(item.forecast_cents > item.budgeted_cents
                      ? { color: 'critical', 'supporting-text': 'Boven begroting' }
                      : {})}
                  />
                  <nldd-text-cell
                    text={covered(item, 'covered_cents')}
                    horizontal-alignment="right"
                  />
                  <nldd-text-cell
                    text={covered(item, 'uncovered_cents')}
                    horizontal-alignment="right"
                  />
                  <nldd-text-cell
                    text={formatPercent(item.pct_total)}
                    horizontal-alignment="right"
                  />
                  <nldd-cell>
                    <Button
                      size="sm"
                      text="Bekijk"
                      accessibleLabel={`Bekijk ${item.description}`}
                      onClick={() => setOpenId(item.id)}
                    />
                  </nldd-cell>
                </nldd-table-row>
              ))}
              <EmptyRows
                text="Er zijn geen kostenposten om te tonen"
                supportingText="Je ziet hier kostenposten die worden gedekt door een opdracht die je beheert."
              />
            </nldd-table>
          </QueryState>
        </nldd-container>
      </nldd-simple-section>

      <CostItemSheet item={opened} onClose={() => setOpenId(null)} />
      <Sheet
        open={adding}
        title="Kostenpost toevoegen"
        dismissText="Annuleer"
        onClose={() => setAdding(false)}
      >
        <NewCostItemForm
          onCreated={async (item) => {
            setAdding(false);
            await queryClient.invalidateQueries({ queryKey: ['costs'] });
            setOpenId(item.id);
          }}
        />
      </Sheet>
    </>
  );
}

function NewCostItemForm({ onCreated }: { onCreated: (item: CostItem) => void }) {
  const [description, setDescription] = useState('');
  const [budgeted, setBudgeted] = useState('');
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: createCostItem,
    onSuccess: onCreated,
    onError: (err) => setError(errorMessage(err)),
  });
  return (
    <Form
      submitText="Voeg toe"
      submitting={create.isPending}
      error={error}
      onSubmit={() => {
        const cents = budgeted.trim() === '' ? 0 : eurosToCents(budgeted);
        if (!description.trim() || cents === null || cents < 0) {
          setError('Vul een omschrijving in, en een begroot bedrag in euro als dat bekend is.');
          return;
        }
        create.mutate({ description, budgeted_cents: cents });
      }}
    >
      <TextField
        label="Omschrijving"
        supportingLabel="Bijvoorbeeld een hostingcontract"
        value={description}
        onChange={setDescription}
        required
      />
      <TextField
        label="Begroot bedrag"
        supportingLabel="In euro"
        optional
        value={budgeted}
        onChange={setBudgeted}
        keyboard="decimal"
      />
    </Form>
  );
}
