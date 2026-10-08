import { ActionBar, type ActionBarFilter } from '@/ui/ActionBar';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatEuro, formatPercent } from '@/lib/format';
import { fetchKpi, kpiKey, setKpiTarget, type Kpi } from './api';
import { Button, TextField } from './ui/controls';
import { percentInput } from './ui/money';
import { Form, Sheet } from './ui/overlays';
import { EmptyRows, QueryState } from './ui/states';

function yearOptions(current: number) {
  return [current - 1, current, current + 1].map((year) => ({
    value: String(year),
    label: String(year),
  }));
}

/**
 * Billability per person for a year: the target, and the realisation split
 * in what is established (closed months) and what is planned (open months).
 */
export function KpiView({ viewFilter }: { viewFilter?: ActionBarFilter }) {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const query = useQuery({ queryKey: kpiKey(year), queryFn: () => fetchKpi(year) });
  const rows = query.data?.items ?? [];
  const mayManage = query.data?.may_manage ?? false;
  const [editing, setEditing] = useState<Kpi | null>(null);

  return (
    <>
      <ActionBar
        label="Weergave en jaar"
        filters={[
          ...(viewFilter ? [viewFilter] : []),
          {
            label: 'Jaar',
            value: String(year),
            onChange: (value) => setYear(Number(value)),
            options: yearOptions(thisYear),
            width: '140px',
          },
        ]}
      />

      <QueryState query={query}>
        <nldd-table
          accessible-label={`KPI per persoon, ${year}`}
          columns={[
            'minmax(180px,2fr)',
            '90px',
            'minmax(120px,1fr)',
            'minmax(120px,1fr)',
            'minmax(120px,1fr)',
            'minmax(120px,1fr)',
            ...(mayManage ? ['130px'] : []),
          ].join(' ')}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Naam" />
            <nldd-text-cell text="Target" horizontal-alignment="right" />
            <nldd-text-cell text="Targetbedrag" horizontal-alignment="right" />
            <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
            <nldd-text-cell text="Nog gepland" horizontal-alignment="right" />
            <nldd-text-cell text="Verwacht totaal" horizontal-alignment="right" />
            {mayManage ? <nldd-text-cell text="Actie" /> : null}
          </nldd-table-row>
          {rows.map((row) => (
            <nldd-table-row key={row.person_id}>
              <nldd-text-cell
                text={row.person_name}
                {...(row.unavailable_reason ? { 'supporting-text': row.unavailable_reason } : {})}
              />
              <nldd-text-cell
                text={row.target_pct === null ? 'Geen' : formatPercent(row.target_pct)}
                horizontal-alignment="right"
              />
              <nldd-text-cell text={formatEuro(row.target_cents)} horizontal-alignment="right" />
              <nldd-text-cell text={formatEuro(row.realised_cents)} horizontal-alignment="right" />
              <nldd-text-cell text={formatEuro(row.forecast_cents)} horizontal-alignment="right" />
              <nldd-text-cell
                text={formatEuro(row.realisation_cents)}
                horizontal-alignment="right"
              />
              {mayManage ? (
                <nldd-cell>
                  <Button
                    size="sm"
                    text="Stel target in"
                    accessibleLabel={`Stel het target van ${row.person_name} in`}
                    onClick={() => setEditing(row)}
                  />
                </nldd-cell>
              ) : null}
            </nldd-table-row>
          ))}
          <EmptyRows
            text="Er is geen KPI om te tonen"
            supportingText="Je ziet hier je eigen KPI en die van medewerkers die aan jou rapporteren."
          />
        </nldd-table>
        <nldd-text-cell
          size="sm"
          color="secondary"
          text="Gerealiseerd telt de afgesloten maanden met de vastgestelde inzet. Nog gepland telt de open maanden met de geplande inzet. Verwacht totaal is de som van beide."
        />
      </QueryState>

      <Sheet
        open={editing !== null}
        title={editing ? `Target ${editing.year} van ${editing.person_name}` : 'Target'}
        dismissText="Annuleer"
        onClose={() => setEditing(null)}
      >
        {editing ? (
          <TargetForm key={editing.person_id} row={editing} onSaved={() => setEditing(null)} />
        ) : null}
      </Sheet>
    </>
  );
}

function TargetForm({ row, onSaved }: { row: Kpi; onSaved: () => void }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(row.target_pct === null ? '' : String(Number(row.target_pct)));
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (pct: string) => setKpiTarget(row.person_id, row.year, pct),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['team', 'kpi'] });
      onSaved();
    },
    onError: (err) => setError(errorMessage(err)),
  });
  return (
    <Form
      submitText="Bewaar target"
      submitting={save.isPending}
      error={error}
      onSubmit={() => {
        const pct = percentInput(value);
        if (pct === null || Number(pct) > 100) {
          setError('Vul een percentage van 0 tot en met 100 in.');
          return;
        }
        save.mutate(pct);
      }}
    >
      <TextField
        label="Target declarabel"
        supportingLabel="Percentage van het jaar dat declarabel moet zijn"
        value={value}
        onChange={setValue}
        keyboard="decimal"
        required
      />
    </Form>
  );
}
