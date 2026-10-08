import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import {
  Button,
  EmptyNotice,
  ErrorNotice,
  FormSheet,
  Loading,
  SectionHeading,
  TextInput,
} from '@/features/assignments/ui';
import { DocumentLink } from '@/features/quotes/ui';
import { formatDateTime } from '@/features/quotes/format';
import { useInstance } from '@/layout/useInstance';
import { formatEuro, formatMonth, formatPercent } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import {
  closeMonth,
  createExport,
  exportCsvUrl,
  fetchExports,
  fetchMonth,
  fetchTimeline,
  monthKeys,
  normalisePercent,
  percentInput,
  reopenMonth,
  type BillingExport,
  type MonthDetail,
  type MonthLine,
  type MonthState,
} from './api';

const MONTH_PARAM = 'maand';

function stateText(state: MonthState): string {
  if (state.closed) return 'Afgesloten';
  return state.closable ? 'Open' : 'Nog niet voorbij';
}

function has(lines: MonthLine[], field: keyof MonthLine): boolean {
  return lines.some((line) => field in line);
}

function PercentCell({
  label,
  value,
  invalid,
  onChange,
}: {
  label: string;
  value: string;
  invalid: boolean;
  onChange: (value: string) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', (event) => {
    const detail = (event as CustomEvent<{ value?: unknown }>).detail;
    const target = event.target as { value?: unknown } | null;
    onChange(String(detail?.value ?? target?.value ?? ''));
  });
  return (
    <nldd-cell>
      <nldd-text-field
        ref={ref}
        size="sm"
        width="96px"
        value={value}
        keyboard="decimal"
        accessible-label={label}
        invalid={orUndef(invalid)}
      />
    </nldd-cell>
  );
}

function MonthTable({
  detail,
  editable,
  edits,
  onEdit,
}: {
  detail: MonthDetail;
  editable: boolean;
  edits: Record<string, string>;
  onEdit: (allocationId: string, value: string) => void;
}) {
  const lines = detail.lines;
  const showPct = has(lines, 'planned_fte_pct');
  const showRate = has(lines, 'category');
  const showEstablished = showPct && (detail.closed || editable);
  const columns = [
    'minmax(160px,1.5fr)',
    'minmax(140px,1.2fr)',
    ...(showPct ? ['100px'] : []),
    ...(showEstablished ? ['130px'] : []),
    ...(showRate ? ['90px', 'minmax(110px,1fr)', 'minmax(110px,1fr)'] : []),
    ...(showRate && detail.closed ? ['minmax(110px,1fr)'] : []),
  ].join(' ');

  return (
    <nldd-table accessible-label={`Inzet in ${formatMonth(detail.month)}`} columns={columns}>
      <nldd-table-row slot="header">
        <nldd-text-cell text="Persoon" />
        <nldd-text-cell text="Rol" />
        {showPct ? <nldd-text-cell text="Gepland" horizontal-alignment="right" /> : null}
        {showEstablished ? (
          <nldd-text-cell text="Vastgesteld" horizontal-alignment="right" />
        ) : null}
        {showRate ? (
          <>
            <nldd-text-cell text="Categorie" />
            <nldd-text-cell text="Maandtarief" horizontal-alignment="right" />
            <nldd-text-cell text="Bedrag gepland" horizontal-alignment="right" />
          </>
        ) : null}
        {showRate && detail.closed ? (
          <nldd-text-cell text="Bedrag vastgesteld" horizontal-alignment="right" />
        ) : null}
      </nldd-table-row>
      {lines.map((line) => {
        const typed = edits[line.allocation_id];
        const value = typed ?? percentInput(line.planned_fte_pct);
        return (
          <nldd-table-row key={line.allocation_id}>
            <nldd-text-cell text={line.person_name} />
            <nldd-text-cell text={line.description} />
            {showPct ? (
              <nldd-text-cell
                text={formatPercent(line.planned_fte_pct)}
                horizontal-alignment="right"
              />
            ) : null}
            {showEstablished && editable ? (
              <PercentCell
                label={`Vastgesteld percentage van ${line.person_name}`}
                value={value}
                invalid={normalisePercent(value) === null}
                onChange={(next) => onEdit(line.allocation_id, next)}
              />
            ) : null}
            {showEstablished && !editable ? (
              <nldd-text-cell
                text={formatPercent(line.established_fte_pct)}
                horizontal-alignment="right"
              />
            ) : null}
            {showRate ? (
              <>
                <nldd-text-cell text={line.category ?? ''} />
                <nldd-text-cell
                  text={formatEuro(line.monthly_rate_cents)}
                  horizontal-alignment="right"
                />
                <nldd-text-cell
                  text={formatEuro(line.planned_amount_cents)}
                  horizontal-alignment="right"
                />
              </>
            ) : null}
            {showRate && detail.closed ? (
              <nldd-text-cell
                text={formatEuro(line.established_amount_cents)}
                horizontal-alignment="right"
              />
            ) : null}
          </nldd-table-row>
        );
      })}
    </nldd-table>
  );
}

function Exports({ exports, month }: { exports: BillingExport[]; month: string }) {
  const ofMonth = exports.filter((run) => run.month === month);
  if (ofMonth.length === 0) {
    return (
      <EmptyNotice
        text="Er is nog geen export van deze maand"
        supportingText="Een export legt de factuurgegevens vast zoals ze naar het financiële systeem gaan."
      />
    );
  }
  return (
    <nldd-table
      accessible-label={`Exports van ${formatMonth(month)}`}
      columns="minmax(160px,1.2fr) minmax(140px,1fr) minmax(120px,1fr) 160px"
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Gemaakt op" />
        <nldd-text-cell text="Door" />
        <nldd-text-cell text="Totaal" horizontal-alignment="right" />
        <nldd-text-cell text="Bestand" />
      </nldd-table-row>
      {ofMonth.map((run) => (
        <nldd-table-row key={run.id}>
          <nldd-text-cell text={formatDateTime(run.created_at)} />
          <nldd-text-cell text={run.exported_by_name ?? ''} />
          <nldd-text-cell text={formatEuro(run.total_cents)} horizontal-alignment="right" />
          <nldd-cell>
            {run.lines.some((line) => 'amount_cents' in line) ? (
              <DocumentLink href={exportCsvUrl(run.id)} text="Download CSV" />
            ) : null}
          </nldd-cell>
        </nldd-table-row>
      ))}
    </nldd-table>
  );
}

/** The monthly close of one assignment: establish the actual inzet per month. */
export function MonthClosePage() {
  const { assignmentId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const instance = useInstance();
  const queryClient = useQueryClient();

  const timeline = useQuery({
    queryKey: monthKeys.timeline(assignmentId),
    queryFn: () => fetchTimeline(assignmentId),
  });
  const months = timeline.data?.months ?? [];
  const requested = searchParams.get(MONTH_PARAM);
  // Without a choice, open the first month that is waiting to be closed.
  const selected =
    months.find((m) => m.month === requested)?.month ??
    months.find((m) => !m.closed && m.closable)?.month ??
    months[0]?.month ??
    null;

  const detail = useQuery({
    queryKey: monthKeys.detail(assignmentId, selected ?? ''),
    queryFn: () => fetchMonth(assignmentId, selected ?? ''),
    enabled: selected !== null,
  });
  const exports = useQuery({
    queryKey: monthKeys.exports(assignmentId),
    queryFn: () => fetchExports(assignmentId),
  });

  const [edits, setEdits] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reopening, setReopening] = useState(false);
  const [reason, setReason] = useState('');
  const [reopenError, setReopenError] = useState<string | null>(null);

  const select = (month: string) => {
    setEdits({});
    setError(null);
    setNotice(null);
    setSearchParams({ [MONTH_PARAM]: month }, { replace: true });
  };

  const run = useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    onSuccess: async () => {
      setEdits({});
      setError(null);
      setReopening(false);
      await queryClient.invalidateQueries({ queryKey: ['months', assignmentId] });
      await queryClient.invalidateQueries({ queryKey: ['assignments'] });
    },
  });

  const data = detail.data;
  const editable = Boolean(data && !data.closed && data.may_close);
  const name = timeline.data?.assignment_name;
  const title = name ? `Maandafsluiting ${name}` : 'Maandafsluiting';

  const close = () => {
    if (!data || !selected) return;
    const established: { allocation_id: string; fte_pct: string }[] = [];
    for (const line of data.lines) {
      const typed = edits[line.allocation_id];
      if (typed === undefined) continue;
      const pct = normalisePercent(typed);
      if (pct === null) {
        setError(
          `Het vastgestelde percentage van ${line.person_name} is geen getal tussen 0 en 100.`,
        );
        return;
      }
      if (Number(pct) !== Number(line.planned_fte_pct)) {
        established.push({ allocation_id: line.allocation_id, fte_pct: pct });
      }
    }
    run.mutate(() => closeMonth(assignmentId, selected, established), {
      onSuccess: () => setNotice(`${formatMonth(selected)} is afgesloten.`),
      onError: (failure) => setError(errorMessage(failure)),
    });
  };

  return (
    <>
      <nldd-simple-section>
        <PageHeading text={title} instanceName={instance?.name} />
        <nldd-link href={`/opdrachten/${assignmentId}`} text="Terug naar de opdracht" size="md" />
        {timeline.isPending ? <Loading /> : null}
        {timeline.isError ? <ErrorNotice message={errorMessage(timeline.error)} /> : null}
        {timeline.data && months.length === 0 ? (
          <EmptyNotice
            text="Deze opdracht heeft nog geen maanden"
            supportingText="Geef de opdracht een periode of zet iemand in; dan verschijnen hier de maanden."
          />
        ) : null}
        {months.length > 0 ? (
          <nldd-table
            accessible-label="Maanden van de opdracht"
            columns="minmax(140px,1.2fr) minmax(120px,1fr) minmax(160px,1.4fr) 110px"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Maand" />
              <nldd-text-cell text="Status" />
              <nldd-text-cell text="Afgesloten" />
              <nldd-text-cell text="Actie" />
            </nldd-table-row>
            {months.map((state) => (
              <nldd-table-row key={state.month}>
                <nldd-text-cell
                  text={formatMonth(state.month)}
                  {...(state.reopen_count > 0
                    ? { 'supporting-text': `${state.reopen_count} keer heropend` }
                    : {})}
                />
                <nldd-cell>
                  <nldd-badge
                    color={state.closed ? 'success' : state.closable ? 'warning' : 'neutral'}
                    text={stateText(state)}
                  />
                </nldd-cell>
                <nldd-text-cell
                  text={
                    state.closed
                      ? [formatDateTime(state.closed_at), state.closed_by_name]
                          .filter(Boolean)
                          .join(', ')
                      : ''
                  }
                />
                <nldd-cell>
                  <Button
                    size="sm"
                    text={state.month === selected ? 'Getoond' : 'Toon'}
                    disabled={state.month === selected}
                    accessibleLabel={`Toon ${formatMonth(state.month)}`}
                    onClick={() => select(state.month)}
                  />
                </nldd-cell>
              </nldd-table-row>
            ))}
          </nldd-table>
        ) : null}
      </nldd-simple-section>

      {selected ? (
        <nldd-simple-section>
          <SectionHeading text={formatMonth(selected)} />
          {notice ? <nldd-banner variant="success" size="sm" text={notice} /> : null}
          {error ? <nldd-banner variant="critical" size="sm" text={error} /> : null}
          {detail.isPending ? <Loading /> : null}
          {detail.isError ? <ErrorNotice message={errorMessage(detail.error)} /> : null}
          {data ? (
            <nldd-container gap="16">
              {data.pricing_problem ? (
                <nldd-banner
                  variant="warning"
                  text="De bedragen van deze maand kunnen niet worden berekend"
                  supporting-text={data.pricing_problem}
                />
              ) : null}
              {data.closed ? (
                <nldd-text>
                  Afgesloten op {formatDateTime(data.closed_at)}
                  {data.closed_by_name ? ` door ${data.closed_by_name}` : ''}. De vastgestelde
                  inzet telt mee in de uitputting en de factuurgegevens.
                </nldd-text>
              ) : (
                <nldd-text>
                  {editable
                    ? 'De geplande inzet staat klaar als voorstel. Pas het percentage aan waar de werkelijke inzet anders was, en sluit de maand af.'
                    : 'Deze maand is nog open. De bedragen hieronder volgen de planning.'}
                </nldd-text>
              )}

              {data.lines.length > 0 ? (
                <MonthTable
                  detail={data}
                  editable={editable}
                  edits={edits}
                  onEdit={(id, value) => setEdits((current) => ({ ...current, [id]: value }))}
                />
              ) : (
                <EmptyNotice
                  text={
                    data.planned_total_cents !== undefined
                      ? 'Je ziet de inzet per persoon niet'
                      : 'In deze maand is niemand ingezet'
                  }
                />
              )}

              {data.planned_total_cents !== undefined ? (
                <nldd-text>
                  Totaal gepland: {formatEuro(data.planned_total_cents)}
                  {data.established_total_cents !== null &&
                  data.established_total_cents !== undefined
                    ? `. Totaal vastgesteld: ${formatEuro(data.established_total_cents)}`
                    : ''}
                  .
                </nldd-text>
              ) : null}

              {!data.closed && !data.closable ? (
                <nldd-text size="sm">
                  Afsluiten kan zodra de maand voorbij is.
                </nldd-text>
              ) : null}

              {data.may_close || data.may_reopen ? (
                <nldd-button-group>
                  {data.may_close ? (
                    <Button
                      text="Sluit maand af"
                      appearance="primary"
                      loading={run.isPending && !reopening}
                      onClick={close}
                    />
                  ) : null}
                  {data.may_reopen ? (
                    <Button
                      text="Heropen maand"
                      onClick={() => {
                        setReopenError(null);
                        setReopening(true);
                      }}
                    />
                  ) : null}
                </nldd-button-group>
              ) : null}

              {data.history.some((record) => record.reopened_at) ? (
                <>
                  <SectionHeading text="Eerdere afsluitingen" level={3} />
                  <nldd-table
                    accessible-label="Eerdere afsluitingen van deze maand"
                    columns="minmax(160px,1fr) minmax(160px,1fr) minmax(200px,2fr)"
                  >
                    <nldd-table-row slot="header">
                      <nldd-text-cell text="Afgesloten" />
                      <nldd-text-cell text="Heropend" />
                      <nldd-text-cell text="Reden" />
                    </nldd-table-row>
                    {data.history
                      .filter((record) => record.reopened_at)
                      .map((record) => (
                        <nldd-table-row key={record.closed_at}>
                          <nldd-text-cell
                            text={formatDateTime(record.closed_at)}
                            {...(record.closed_by_name
                              ? { 'supporting-text': record.closed_by_name }
                              : {})}
                          />
                          <nldd-text-cell
                            text={formatDateTime(record.reopened_at)}
                            {...(record.reopened_by_name
                              ? { 'supporting-text': record.reopened_by_name }
                              : {})}
                          />
                          <nldd-text-cell text={record.reopen_reason ?? ''} />
                        </nldd-table-row>
                      ))}
                  </nldd-table>
                </>
              ) : null}
            </nldd-container>
          ) : null}
        </nldd-simple-section>
      ) : null}

      {selected && data?.closed ? (
        <nldd-simple-section>
          <SectionHeading text="Factuurgegevens" />
          <nldd-container gap="16">
            <nldd-text>
              Grip maakt geen facturen. Een export legt de vastgestelde inzet van deze maand
              vast als gegevens voor het financiële systeem.
            </nldd-text>
            {exports.isPending ? <Loading /> : null}
            {exports.isError ? <ErrorNotice message={errorMessage(exports.error)} /> : null}
            {exports.data ? <Exports exports={exports.data.exports} month={selected} /> : null}
            {data.lines.some((line) => 'established_amount_cents' in line) ? (
              <nldd-button-group>
                <Button
                  text="Maak export"
                  loading={run.isPending}
                  onClick={() =>
                    run.mutate(() => createExport(assignmentId, selected), {
                      onSuccess: () => setNotice('De export is gemaakt.'),
                      onError: (failure) => setError(errorMessage(failure)),
                    })
                  }
                />
              </nldd-button-group>
            ) : null}
          </nldd-container>
        </nldd-simple-section>
      ) : null}

      <FormSheet
        open={reopening}
        title="Maand heropenen"
        submitText="Heropen"
        busy={run.isPending && reopening}
        error={reopenError}
        onClose={() => setReopening(false)}
        onSubmit={() => {
          if (!selected) return;
          if (!reason.trim()) {
            setReopenError('Geef een reden voor het heropenen.');
            return;
          }
          run.mutate(() => reopenMonth(assignmentId, selected, reason.trim()), {
            onSuccess: () => {
              setReason('');
              setNotice(`${formatMonth(selected)} is heropend.`);
            },
            onError: (failure) => setReopenError(errorMessage(failure)),
          });
        }}
      >
        <nldd-text>
          Na heropenen telt deze maand weer met de geplande inzet, tot de maand opnieuw wordt
          afgesloten. De eerdere afsluiting en de reden blijven bewaard.
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} required multiline />
      </FormSheet>
    </>
  );
}
