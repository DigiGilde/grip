import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { MoneyCell } from '@/features/reports/ui';
import { formatEuro, formatPercent } from '@/lib/format';
import { Quiet } from '@/ui/layout';
import { ROW_ACTIONS_COLUMN, RowActions, RowActionsHeader } from '@/ui/RowActions';
import { useStaleChoice } from '@/ui/stale';
import { fetchKpi, kpiKey, setKpiTarget, targetKey, type Kpi } from './api';
import { TextField } from './ui/controls';
import { percentInput } from './ui/money';
import { Form, Sheet } from './ui/overlays';
import { EmptyRows, QueryState } from './ui/states';

const COLUMNS = [
  'minmax(180px,2fr)',
  '190px',
  '90px',
  'minmax(120px,1fr)',
  'minmax(120px,1fr)',
  'minmax(120px,1fr)',
  'minmax(120px,1fr)',
];
const NARROW_COLUMNS = 'minmax(120px,1fr) minmax(140px,max-content)';
/** The table width in rem up to which `hide-below="md"` hides a column. */
const DETAIL_COLUMNS_HIDDEN_UP_TO = 40;

/** Whether the table is too narrow for its detail columns, measured on the table itself. */
function useDetailColumnsHidden() {
  const ref = useRef<HTMLElement>(null);
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    const table = ref.current;
    if (!table || typeof ResizeObserver === 'undefined') return;
    const measure = () => {
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      setHidden(table.getBoundingClientRect().width <= DETAIL_COLUMNS_HIDDEN_UP_TO * rem);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(table);
    return () => observer.disconnect();
  });
  return [ref, hidden] as const;
}

/** An amount that leaves the table below the medium width, with its header. */
function Amount({ cents, bold }: { cents: number | null; bold?: boolean }) {
  const text = formatEuro(cents);
  return (
    <nldd-text-cell
      text={bold && text ? `**${text}**` : text}
      horizontal-alignment="right"
      hide-below="md"
    />
  );
}

/**
 * Billability per person for a year, below target first: the outcome against
 * the target, and the realisation split in what is established (closed
 * months) and what is planned (open months).
 */
export function KpiView({ year: yearText }: { year: string }) {
  const year = Number(yearText);
  const query = useQuery({ queryKey: kpiKey(year), queryFn: () => fetchKpi(year) });
  const rows = query.data?.items ?? [];
  const mayManage = query.data?.may_manage ?? false;
  const totals = query.data?.totals ?? null;
  const [editing, setEditing] = useState<Kpi | null>(null);
  const [tableRef, detailHidden] = useDetailColumnsHidden();

  return (
    <>
      <QueryState query={query}>
        <nldd-table
          ref={tableRef}
          accessible-label={`KPI per persoon, ${year}`}
          columns={[...COLUMNS, ...(mayManage ? [ROW_ACTIONS_COLUMN] : [])].join(' ')}
          sm-columns={mayManage ? `${NARROW_COLUMNS} ${ROW_ACTIONS_COLUMN}` : NARROW_COLUMNS}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Persoon" />
            <nldd-text-cell text="Ten opzichte van target" horizontal-alignment="right" />
            <nldd-text-cell text="Target" horizontal-alignment="right" hide-below="md" />
            <nldd-text-cell text="Targetbedrag" horizontal-alignment="right" hide-below="md" />
            <nldd-text-cell
              text="Gerealiseerde inzet"
              horizontal-alignment="right"
              hide-below="md"
            />
            <nldd-text-cell text="Nog gepland" horizontal-alignment="right" hide-below="md" />
            <nldd-text-cell text="Verwacht totaal" horizontal-alignment="right" hide-below="md" />
            {mayManage ? <RowActionsHeader /> : null}
          </nldd-table-row>
          {rows.map((row) => (
            <nldd-table-row key={row.person_id}>
              <nldd-text-cell
                row-header
                text={row.person_name}
                {...(row.unavailable_reason ? { 'supporting-text': row.unavailable_reason } : {})}
              />
              <GapCell row={row} />
              <nldd-text-cell
                text={row.target_pct === null ? 'Geen' : formatPercent(row.target_pct)}
                horizontal-alignment="right"
                hide-below="md"
              />
              <Amount cents={row.target_cents} />
              <Amount cents={row.realised_cents} />
              <Amount cents={row.forecast_cents} />
              <Amount cents={row.realisation_cents} />
              {mayManage ? (
                <RowActions
                  name={row.person_name}
                  actions={[{ text: 'Stel target in', onSelect: () => setEditing(row) }]}
                />
              ) : null}
            </nldd-table-row>
          ))}
          {totals && rows.length > 0 ? (
            <nldd-table-row>
              <nldd-text-cell row-header text="**Totaal**" />
              {typeof totals.gap_cents === 'number' ? (
                <MoneyCell cents={totals.gap_cents} bold critical={totals.gap_cents < 0} />
              ) : (
                <nldd-text-cell />
              )}
              <nldd-text-cell hide-below="md" />
              <Amount bold cents={totals.target_cents} />
              <Amount bold cents={totals.realised_cents} />
              <Amount bold cents={totals.forecast_cents} />
              <Amount bold cents={totals.realisation_cents} />
              {mayManage ? <nldd-cell /> : null}
            </nldd-table-row>
          ) : null}
          <EmptyRows
            text="Er is geen KPI om te tonen"
            supportingText="Je ziet hier je eigen KPI en die van medewerkers die aan jou rapporteren."
          />
        </nldd-table>
        {detailHidden ? null : (
          <Quiet>
            Gerealiseerde inzet telt de afgesloten maanden met de vastgestelde inzet. Nog gepland
            telt de open maanden met de geplande inzet. Verwacht totaal is de som van beide.
          </Quiet>
        )}
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

/** Against the target, as the server worked it out: said in words, never in colour alone. */
function GapCell({ row }: { row: Kpi }) {
  if (row.gap_cents === null) {
    return (
      <nldd-text-cell
        text={row.unavailable_reason ? 'Niet berekend' : 'Geen target'}
        horizontal-alignment="right"
        color="secondary"
      />
    );
  }
  return row.gap_cents < 0 ? (
    <MoneyCell cents={row.gap_cents} critical note="Onder target" />
  ) : (
    <MoneyCell cents={row.gap_cents} note="Op of boven target" />
  );
}

function TargetForm({ row, onSaved }: { row: Kpi; onSaved: () => void }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(row.target_pct === null ? '' : String(Number(row.target_pct)));
  const [error, setError] = useState<string | null>(null);
  const stale = useStaleChoice(targetKey(row.person_id, row.year), row.target_version, () =>
    queryClient.invalidateQueries({ queryKey: ['team', 'kpi'] }),
  );
  const [sent, setSent] = useState('');
  const save = useMutation({
    mutationFn: ({ pct, onTop }: { pct: string; onTop?: boolean }) =>
      setKpiTarget(row.person_id, row.year, pct, onTop ? stale.latestHeaders : stale.headers),
    onSuccess: async () => {
      stale.saved();
      await queryClient.invalidateQueries({ queryKey: ['team', 'kpi'] });
      onSaved();
    },
    onError: async (err) => {
      if (!(await stale.caught(err))) setError(errorMessage(err));
    },
  });
  return (
    <Form
      submitText="Bewaar target"
      submitting={save.isPending}
      error={error}
      conflict={
        stale.conflict
          ? {
              conflict: stale.conflict,
              keepMine: () => save.mutate({ pct: sent, onTop: true }),
              takeTheirs: onSaved,
            }
          : null
      }
      onSubmit={() => {
        const pct = percentInput(value);
        if (pct === null || Number(pct) > 100) {
          setError('Vul een percentage van 0 tot en met 100 in.');
          return;
        }
        setSent(pct);
        save.mutate({ pct });
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
