import { useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { Button, TextInput } from '@/features/assignments/ui';
import { formatDateTime } from '@/features/quotes/format';
import { formatEuro, formatMonth, formatPercent } from '@/lib/format';
import { ErrorNotice, FormSheet, Loading, Quiet, Stack } from '@/ui/layout';
import {
  closeMonth,
  fetchMonth,
  monthKeys,
  normalisePercent,
  percentInput,
  reopenMonth,
  type MonthDetail,
  type MonthLine,
} from './api';

/** A sheet to read in: no form, no primary button. */
function ViewSheet({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const sheetRef = useRef<HTMLElement>(null);
  const barRef = useRef<HTMLElement>(null);
  const titleId = useId();
  useNlddEvent(sheetRef, 'close', onClose);
  useNlddEvent(barRef, 'dismiss', onClose);
  return createPortal(
    <nldd-sheet ref={sheetRef} open={orUndef(open)} placement="right" width="640px">
      <nldd-page>
        <nldd-top-title-bar
          ref={barRef}
          slot="header"
          text={title}
          dismiss-text="Sluit"
          collapse-anchor={titleId}
        />
        <nldd-simple-section>
          <nldd-title id={titleId} slot="header" size={2} text={title} heading-level={1} />
          <nldd-container gap="24">{children}</nldd-container>
        </nldd-simple-section>
      </nldd-page>
    </nldd-sheet>,
    document.body,
  );
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

/** Whether what was worked differs from what was planned, as numbers. */
function differs(planned: string | undefined, worked: string | null | undefined): boolean {
  if (planned === undefined || worked === null || worked === undefined) return false;
  const typed = normalisePercent(worked);
  return typed !== null && Number(typed) !== Number(planned);
}

/**
 * Who worked how much in the month. What equals the plan is quiet; what
 * differs carries the planned figure next to it, so the eye finds it.
 */
function WorkTable({
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
  const showAmount = has(lines, 'planned_amount_cents');
  const columns = [
    'minmax(180px,2fr)',
    ...(showPct ? ['130px'] : []),
    ...(showAmount ? ['minmax(110px,1fr)'] : []),
  ].join(' ');
  return (
    <nldd-table accessible-label={`Inzet in ${formatMonth(detail.month)}`} columns={columns}>
      <nldd-table-row slot="header">
        <nldd-text-cell text="Wie" />
        {showPct ? <nldd-text-cell text="Gewerkt" horizontal-alignment="right" /> : null}
        {showAmount ? <nldd-text-cell text="Bedrag" horizontal-alignment="right" /> : null}
      </nldd-table-row>
      {lines.map((line) => {
        const typed = edits[line.allocation_id];
        const value = typed ?? percentInput(line.planned_fte_pct);
        const worked = editable ? value : line.established_fte_pct;
        const changed = differs(line.planned_fte_pct, worked);
        const amount = detail.closed ? line.established_amount_cents : line.planned_amount_cents;
        return (
          <nldd-table-row key={line.allocation_id}>
            <nldd-text-cell
              text={line.person_name}
              supporting-text={
                changed
                  ? `${line.description} · gepland ${formatPercent(line.planned_fte_pct)}`
                  : line.description
              }
              {...(changed ? { color: 'warning' } : {})}
            />
            {showPct && editable ? (
              <PercentCell
                label={`Gewerkt percentage van ${line.person_name}`}
                value={value}
                invalid={normalisePercent(value) === null}
                onChange={(next) => onEdit(line.allocation_id, next)}
              />
            ) : null}
            {showPct && !editable ? (
              <nldd-text-cell
                text={formatPercent(
                  detail.closed ? line.established_fte_pct : line.planned_fte_pct,
                )}
                horizontal-alignment="right"
                {...(changed ? { color: 'warning' } : {})}
              />
            ) : null}
            {showAmount ? (
              <nldd-text-cell
                text={amount === null || amount === undefined ? '' : formatEuro(amount)}
                horizontal-alignment="right"
              />
            ) : null}
          </nldd-table-row>
        );
      })}
    </nldd-table>
  );
}

interface MonthSheetProps {
  assignmentId: string;
  /** YYYY-MM, or null when the sheet is closed. */
  month: string | null;
  onClose: () => void;
}

/**
 * One month, on demand. An open month asks one question: does this match
 * what was worked? A closed month shows what was settled, and lets who may
 * reopen it.
 */
export function MonthSheet({ assignmentId, month, onClose }: MonthSheetProps) {
  const queryClient = useQueryClient();
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [reopening, setReopening] = useState(false);
  const [reason, setReason] = useState('');
  // The sheet stays in the page while closed; it remembers its last month so
  // it does not empty while it slides away.
  const [last, setLast] = useState<string | null>(month);
  if (month !== null && month !== last) {
    setLast(month);
    setEdits({});
    setError(null);
    setReopening(false);
    setReason('');
  }
  const shown = month ?? last;

  const detail = useQuery({
    queryKey: monthKeys.detail(assignmentId, shown ?? ''),
    queryFn: () => fetchMonth(assignmentId, shown ?? ''),
    enabled: shown !== null,
  });
  const data = detail.data;

  const run = useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['months', assignmentId] });
      await queryClient.invalidateQueries({ queryKey: ['assignments'] });
      await queryClient.invalidateQueries({ queryKey: ['billing'] });
      await queryClient.invalidateQueries({ queryKey: ['tasks'] });
      onClose();
    },
    onError: (failure) => setError(errorMessage(failure)),
  });

  const name = shown ? formatMonth(shown) : '';
  const editable = Boolean(data && !data.closed && data.may_close);

  const close = () => {
    if (!data || !shown) return;
    const established: { allocation_id: string; fte_pct: string }[] = [];
    for (const line of data.lines) {
      const typed = edits[line.allocation_id];
      if (typed === undefined) continue;
      const pct = normalisePercent(typed);
      if (pct === null) {
        setError(`Het percentage van ${line.person_name} is geen getal tussen 0 en 100.`);
        return;
      }
      if (Number(pct) !== Number(line.planned_fte_pct)) {
        established.push({ allocation_id: line.allocation_id, fte_pct: pct });
      }
    }
    run.mutate(() => closeMonth(assignmentId, shown, established));
  };

  const body = (
    <>
      {detail.isPending && shown ? <Loading /> : null}
      {detail.isError ? <ErrorNotice message={errorMessage(detail.error)} /> : null}
      {data?.pricing_problem ? (
        <nldd-banner
          variant="warning"
          size="sm"
          text="De bedragen van deze maand kunnen niet worden berekend"
          supporting-text={data.pricing_problem}
        />
      ) : null}
      {data && data.lines.length > 0 ? (
        <WorkTable
          detail={data}
          editable={editable}
          edits={edits}
          onEdit={(id, value) => setEdits((current) => ({ ...current, [id]: value }))}
        />
      ) : null}
      {data && data.lines.length === 0 ? (
        <nldd-text>In deze maand was niemand ingezet.</nldd-text>
      ) : null}
    </>
  );

  if (editable) {
    return (
      <FormSheet
        open={month !== null}
        title={`Klopt dit met wat er in ${name} is gewerkt?`}
        submitText={`Sluit ${name} af`}
        size="wide"
        busy={run.isPending}
        error={error}
        onClose={onClose}
        onSubmit={close}
      >
        {body}
        <Quiet>Werkte iemand meer of minder, pas dan het percentage aan.</Quiet>
      </FormSheet>
    );
  }

  if (reopening && data?.may_reopen) {
    return (
      <FormSheet
        open={month !== null}
        title={`Heropen ${name}`}
        submitText="Heropen"
        busy={run.isPending}
        error={error}
        onClose={onClose}
        onSubmit={() => {
          if (!shown) return;
          if (!reason.trim()) {
            setError('Geef een reden voor het heropenen.');
            return;
          }
          run.mutate(() => reopenMonth(assignmentId, shown, reason.trim()));
        }}
      >
        <nldd-text>
          Na heropenen telt deze maand weer met de geplande inzet, tot de maand opnieuw wordt
          afgesloten. De eerdere afsluiting en de reden blijven bewaard.
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} required multiline />
      </FormSheet>
    );
  }

  const reopened = (data?.history ?? []).filter((record) => record.reopened_at);
  return (
    <ViewSheet
      open={month !== null && (data !== undefined || detail.isError)}
      title={name ? name.charAt(0).toUpperCase() + name.slice(1) : ''}
      onClose={onClose}
    >
      {error ? <ErrorNotice message={error} /> : null}
      {body}
      {data?.closed ? (
        <Quiet>
          Afgesloten op {formatDateTime(data.closed_at)}
          {data.closed_by_name ? ` door ${data.closed_by_name}` : ''}
        </Quiet>
      ) : null}
      {reopened.length > 0 ? (
        <Stack gap="close">
          {reopened.map((record) => (
            <Quiet key={record.closed_at}>
              Heropend op {formatDateTime(record.reopened_at)}
              {record.reopened_by_name ? ` door ${record.reopened_by_name}` : ''}
              {record.reopen_reason ? `: ${record.reopen_reason}` : ''}
            </Quiet>
          ))}
        </Stack>
      ) : null}
      {data?.may_reopen ? (
        <nldd-button-group>
          <Button
            text="Heropen"
            accessibleLabel={`Heropen ${name}`}
            onClick={() => {
              setError(null);
              setReopening(true);
            }}
          />
        </nldd-button-group>
      ) : null}
    </ViewSheet>
  );
}
