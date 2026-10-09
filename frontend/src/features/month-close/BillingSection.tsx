import { useStaleForm } from '@/ui/useStaleForm';
import { RowActions, ROW_ACTIONS_COLUMN } from '@/ui/RowActions';
import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { centsToInput, parseEuroToCents } from '@/features/assignments/money';
import { DateInput, TextInput } from '@/features/assignments/ui';
import { formatDateTime } from '@/features/quotes/format';
import { formatDate, formatEuro, formatMonth } from '@/lib/format';
import { FormSheet, Section } from '@/ui/layout';
import {
  billingKey,
  correctInvoice,
  fetchInvoiceProposal,
  recordInvoice,
  withdrawInvoice,
  type BillingStatus,
  type MonthBilling,
  type OutgoingInvoice,
} from './api';
import { differenceText } from './billingText';
import '@/features/quotes/register';

function monthsText(months: readonly string[]): string {
  return months.map((month) => formatMonth(month)).join(', ');
}

/** Aangeleverd and gefactureerd of the whole assignment, as four figures. */
export function BillingTotals({ status }: { status: BillingStatus }) {
  if (status.delivered_cents === undefined) return null;
  const toDeliver = status.to_deliver_cents;
  const toInvoice = status.to_invoice_cents ?? 0;
  return (
    <nldd-table
      accessible-label="Aangeleverd en gefactureerd, hele opdracht"
      columns="repeat(4, minmax(140px, 1fr))"
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Aangeleverd" horizontal-alignment="right" />
        <nldd-text-cell text="Nog aan te leveren" horizontal-alignment="right" />
        <nldd-text-cell text="Gefactureerd" horizontal-alignment="right" />
        <nldd-text-cell text="Nog te factureren" horizontal-alignment="right" />
      </nldd-table-row>
      <nldd-table-row>
        <nldd-text-cell text={formatEuro(status.delivered_cents)} horizontal-alignment="right" />
        <nldd-text-cell
          text={
            toDeliver === null || toDeliver === undefined
              ? 'Niet te berekenen'
              : formatEuro(toDeliver)
          }
          horizontal-alignment="right"
        />
        <nldd-text-cell text={formatEuro(status.invoiced_cents)} horizontal-alignment="right" />
        <nldd-text-cell
          text={formatEuro(toInvoice)}
          {...(toInvoice < 0
            ? { 'supporting-text': 'Meer gefactureerd dan aangeleverd', color: 'critical' }
            : {})}
          horizontal-alignment="right"
        />
      </nldd-table-row>
    </nldd-table>
  );
}

type InvoiceDialog =
  | { kind: 'record'; months: string[] }
  | { kind: 'correct'; invoice: OutgoingInvoice }
  | { kind: 'withdraw'; invoice: OutgoingInvoice }
  | null;

function MonthChoice({
  month,
  checked,
  onChange,
}: {
  month: MonthBilling;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => {
    const detail = (event as CustomEvent<{ checked?: boolean }>).detail;
    onChange(Boolean(detail?.checked));
  });
  return (
    <nldd-checkbox-field
      ref={ref}
      checked={orUndef(checked)}
      label={`${formatMonth(month.month)}, aangeleverd ${formatEuro(month.delivered_cents)}`}
    />
  );
}

interface InvoicesProps {
  assignmentId: string;
  status: BillingStatus;
  /** Months to record an invoice for right away, from the address or a row. */
  recordFor: string[] | null;
  onRecordDone: () => void;
}

/**
 * The recorded invoices of an assignment, and the sheets to record, correct
 * or withdraw one. Grip sends no invoice; this is where someone says that
 * one was sent.
 */
export function Invoices({ assignmentId, status, recordFor, onRecordDone }: InvoicesProps) {
  const queryClient = useQueryClient();
  const months = status.months ?? [];
  const invoices = status.invoices ?? [];
  const mayRecord = Boolean(status.may_record_invoice);
  // Only deliveries that are in force and carry no invoice can be chosen.
  const open = months.filter((m) => m.state === 'delivered' && m.export_id);

  const [dialog, setDialog] = useState<InvoiceDialog>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [number, setNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState('');
  // Undefined until the person types: the field then shows what was delivered.
  const [amount, setAmount] = useState<string | undefined>(undefined);
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');

  // A row or the address asks to record an invoice for these months. The
  // sheet follows that request: a new request starts with empty fields.
  const requested = mayRecord && recordFor ? recordFor.join(',') : null;
  const [seen, setSeen] = useState<string | null>(null);
  if (requested !== seen) {
    setSeen(requested);
    if (requested !== null) {
      const wanted = requested.split(',');
      setChosen(open.filter((m) => wanted.includes(m.month)).map((m) => m.month));
      setNumber('');
      setInvoiceDate('');
      setAmount(undefined);
      setNote('');
      setFormError(null);
      setDialog({ kind: 'record', months: wanted });
    }
  }

  const selection = open.filter((m) => chosen.includes(m.month));
  const exportIds = selection.map((m) => m.export_id as string);
  const proposal = useQuery({
    queryKey: [...billingKey(assignmentId), 'proposal', ...exportIds],
    queryFn: () => fetchInvoiceProposal(assignmentId, exportIds),
    enabled: dialog?.kind === 'record' && exportIds.length > 0,
  });

  const close = () => {
    setDialog(null);
    onRecordDone();
  };
  const run = useMutation({
    mutationFn: (action: () => Promise<BillingStatus>) => action(),
    onSuccess: async (updated) => {
      queryClient.setQueryData(billingKey(assignmentId), updated);
      setFormError(null);
      close();
      await queryClient.invalidateQueries({ queryKey: ['assignments'] });
      await queryClient.invalidateQueries({ queryKey: ['reports'] });
      await queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (failure) => setFormError(errorMessage(failure)),
  });

  const edit = (next: InvoiceDialog) => {
    setFormError(null);
    if (next?.kind === 'correct') {
      setNumber(next.invoice.invoice_number);
      setInvoiceDate(next.invoice.invoice_date);
      setAmount(centsToInput(next.invoice.amount_cents));
      setNote(next.invoice.note ?? '');
    }
    if (next?.kind === 'withdraw') setReason('');
    setDialog(next);
  };

  const proposed = proposal.data ? centsToInput(proposal.data.delivered_cents) : '';
  const amountText = amount ?? (dialog?.kind === 'record' ? proposed : '');

  /** The typed fields as the API takes them, or null after saying what is wrong. */
  const fields = () => {
    if (!number.trim()) {
      setFormError('Vul het factuurnummer in.');
      return null;
    }
    if (!invoiceDate) {
      setFormError('Vul de factuurdatum in.');
      return null;
    }
    const cents = parseEuroToCents(amountText);
    if (cents === null) {
      setFormError('Vul het factuurbedrag in als bedrag in euro, bijvoorbeeld 14.400,00.');
      return null;
    }
    return {
      invoice_number: number.trim(),
      invoice_date: invoiceDate,
      amount_cents: cents,
      note: note.trim() || null,
    };
  };

  const inForce = invoices.filter((invoice) => !invoice.withdrawn_at);
  const withdrawn = invoices.filter((invoice) => invoice.withdrawn_at);
  const correcting = dialog?.kind === 'correct' ? dialog.invoice : null;
  const withdrawing = dialog?.kind === 'withdraw' ? dialog.invoice : null;
  // A correction is saved on the invoice as the sheet found it.
  const correction = useStaleForm({
    recordKey: correcting?.id,
    version: invoices.find((invoice) => invoice.id === correcting?.id)?.version,
    restart: correcting?.id ?? null,
    save: (input: NonNullable<ReturnType<typeof fields>>, headers) =>
      correctInvoice(correcting?.id ?? '', input, headers),
    refresh: () => queryClient.invalidateQueries({ queryKey: billingKey(assignmentId) }),
    onSaved: async (updated) => {
      queryClient.setQueryData(billingKey(assignmentId), updated);
      setFormError(null);
      close();
      await queryClient.invalidateQueries({ queryKey: ['assignments'] });
      await queryClient.invalidateQueries({ queryKey: ['reports'] });
      await queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: setFormError,
    onTakeTheirs: close,
  });

  return (
    <>
      {inForce.length > 0 ? (
        <Section title="Facturen" level={2}>
          <nldd-table
            accessible-label="Vastgelegde facturen"
            columns={`minmax(160px,1.4fr) minmax(160px,1.6fr) minmax(200px,2fr) minmax(120px,1fr) ${ROW_ACTIONS_COLUMN}`}
            sm-columns={`minmax(140px,1fr) minmax(100px,auto) ${ROW_ACTIONS_COLUMN}`}
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Factuur" />
              <nldd-text-cell hide-below="md" text="Over" />
              <nldd-text-cell hide-below="md" text="Vergeleken met aangeleverd" />
              <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
              <nldd-cell />
            </nldd-table-row>
            {inForce.map((invoice) => (
              <nldd-table-row key={invoice.id}>
                <nldd-text-cell
                  text={invoice.invoice_number}
                  supporting-text={formatDate(invoice.invoice_date)}
                />
                <nldd-text-cell
                  hide-below="md"
                  size="sm"
                  color="secondary"
                  text={monthsText(invoice.months)}
                />
                <nldd-text-cell
                  hide-below="md"
                  size="sm"
                  text={differenceText(invoice)}
                  color={invoice.difference_cents !== 0 ? 'warning' : 'secondary'}
                />
                <nldd-text-cell
                  text={`**${formatEuro(invoice.amount_cents)}**`}
                  horizontal-alignment="right"
                />
                <RowActions
                  name={`factuur ${invoice.invoice_number}`}
                  actions={
                    mayRecord
                      ? [
                          { text: 'Corrigeer', onSelect: () => edit({ kind: 'correct', invoice }) },
                          { text: 'Trek in', onSelect: () => edit({ kind: 'withdraw', invoice }) },
                        ]
                      : []
                  }
                />
              </nldd-table-row>
            ))}
          </nldd-table>
        </Section>
      ) : null}

      {withdrawn.length > 0 ? (
        <Section title="Ingetrokken facturen" level={2}>
          <nldd-table
            accessible-label="Ingetrokken facturen"
            columns="minmax(120px,1fr) minmax(110px,1fr) minmax(110px,1fr) minmax(240px,2.4fr)"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Factuurnummer" />
              <nldd-text-cell text="Factuurdatum" />
              <nldd-text-cell text="Factuurbedrag" horizontal-alignment="right" />
              <nldd-text-cell text="Ingetrokken" />
            </nldd-table-row>
            {withdrawn.map((invoice) => (
              <nldd-table-row key={invoice.id}>
                <nldd-text-cell text={invoice.invoice_number} />
                <nldd-text-cell text={formatDate(invoice.invoice_date)} />
                <nldd-text-cell
                  text={formatEuro(invoice.amount_cents)}
                  horizontal-alignment="right"
                />
                <nldd-text-cell
                  text={invoice.withdrawn_reason ?? ''}
                  supporting-text={`${invoice.withdrawn_by_name ?? 'Onbekend'}, ${formatDateTime(invoice.withdrawn_at)}`}
                />
              </nldd-table-row>
            ))}
          </nldd-table>
        </Section>
      ) : null}

      <FormSheet
        open={dialog?.kind === 'record'}
        title="Factuur vastleggen"
        submitText="Leg vast"
        busy={run.isPending}
        error={dialog?.kind === 'record' ? formError : null}
        onClose={close}
        onSubmit={() => {
          if (exportIds.length === 0) {
            setFormError('Kies minstens een maand waarvoor de factuur is verstuurd.');
            return;
          }
          const input = fields();
          if (!input) return;
          run.mutate(() => recordInvoice(assignmentId, { ...input, export_ids: exportIds }));
        }}
      >
        <nldd-text>
          Grip verstuurt geen facturen. Hier leg je vast dat de factuur is verstuurd.
        </nldd-text>
        {open.length > 1 ? (
          <nldd-container gap="8">
            {open.map((month) => (
              <MonthChoice
                key={month.month}
                month={month}
                checked={chosen.includes(month.month)}
                onChange={(checked) => {
                  setAmount(undefined);
                  setChosen((current) =>
                    checked
                      ? [...current.filter((m) => m !== month.month), month.month]
                      : current.filter((m) => m !== month.month),
                  );
                }}
              />
            ))}
          </nldd-container>
        ) : (
          <nldd-text>
            {selection[0]
              ? `${formatMonth(selection[0].month)}, aangeleverd ${formatEuro(selection[0].delivered_cents)}`
              : ''}
          </nldd-text>
        )}
        <TextInput label="Factuurnummer" value={number} onChange={setNumber} required />
        <DateInput label="Factuurdatum" value={invoiceDate} onChange={setInvoiceDate} required />
        <TextInput
          label="Factuurbedrag"
          hint={
            proposal.data
              ? `Aangeleverd voor deze maanden: ${formatEuro(proposal.data.delivered_cents)}. Een verschil blijft zichtbaar.`
              : 'In euro, zoals het op de factuur staat'
          }
          value={amountText}
          onChange={setAmount}
          keyboard="decimal"
          required
        />
        <TextInput label="Toelichting" value={note} onChange={setNote} optional multiline />
      </FormSheet>

      <FormSheet
        open={dialog?.kind === 'correct'}
        title="Factuur corrigeren"
        submitText="Bewaar correctie"
        busy={correction.busy}
        error={dialog?.kind === 'correct' ? formError : null}
        onClose={close}
        onSubmit={() => {
          if (!correcting) return;
          const input = fields();
          if (!input) return;
          correction.run(input);
        }}
      >
        {correction.panel}
        <nldd-text>
          De oude en de nieuwe waarden komen in de auditlog te staan, met jouw naam.
        </nldd-text>
        <TextInput label="Factuurnummer" value={number} onChange={setNumber} required />
        <DateInput label="Factuurdatum" value={invoiceDate} onChange={setInvoiceDate} required />
        <TextInput
          label="Factuurbedrag"
          hint="In euro, zoals het op de factuur staat"
          value={amountText}
          onChange={setAmount}
          keyboard="decimal"
          required
        />
        <TextInput label="Toelichting" value={note} onChange={setNote} optional multiline />
      </FormSheet>

      <FormSheet
        open={dialog?.kind === 'withdraw'}
        title="Factuur intrekken"
        submitText="Trek in"
        busy={run.isPending}
        error={dialog?.kind === 'withdraw' ? formError : null}
        onClose={close}
        onSubmit={() => {
          if (!withdrawing) return;
          if (!reason.trim()) {
            setFormError('Geef een reden voor het intrekken.');
            return;
          }
          run.mutate(() => withdrawInvoice(withdrawing.id, reason.trim()));
        }}
      >
        <nldd-text>
          Voor een factuur die hier ten onrechte is vastgelegd. De maanden staan daarna weer als
          aangeleverd. De vastlegging en de reden blijven bewaard.
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} required multiline />
      </FormSheet>
    </>
  );
}
