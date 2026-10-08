import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { centsToInput, parseEuroToCents } from '@/features/assignments/money';
import { Button, DateInput, TextInput } from '@/features/assignments/ui';
import { EmptyNotice, ErrorNotice, FormSheet, Loading, SectionHeading } from '@/ui/layout';
import { formatDateTime } from '@/features/quotes/format';
import { formatDate, formatEuro, formatMonth } from '@/lib/format';
import {
  billingKey,
  correctInvoice,
  fetchBillingStatus,
  fetchInvoiceProposal,
  recordInvoice,
  withdrawInvoice,
  type BillingStatus,
  type MonthBilling,
  type OutgoingInvoice,
} from './api';
import { billingStateRemark, billingStateText, differenceText } from './billingText';
import '@/features/quotes/register';

type Dialog =
  | { kind: 'record' }
  | { kind: 'correct'; invoice: OutgoingInvoice }
  | { kind: 'withdraw'; invoice: OutgoingInvoice }
  | null;

const STATE_COLORS: Record<MonthBilling['state'], 'neutral' | 'accent' | 'success'> = {
  not_delivered: 'neutral',
  delivered: 'accent',
  invoiced: 'success',
};

const STATE_LABELS: Record<MonthBilling['state'], string> = {
  not_delivered: 'Niet aangeleverd',
  delivered: 'Aangeleverd',
  invoiced: 'Gefactureerd',
};

function monthsText(months: string[]): string {
  return months.map((month) => formatMonth(month)).join(', ');
}

function ChooseCell({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => {
    const detail = (event as CustomEvent<{ checked?: boolean }>).detail;
    onChange(Boolean(detail?.checked));
  });
  return (
    <nldd-cell>
      <nldd-checkbox ref={ref} checked={orUndef(checked)} accessible-label={label} />
    </nldd-cell>
  );
}

function Totals({ status }: { status: BillingStatus }) {
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
          text={toDeliver === null || toDeliver === undefined ? 'Niet te berekenen' : formatEuro(toDeliver)}
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

/**
 * Per closed month whether its billing data was delivered and whether an
 * invoice was recorded, and the place to record one.
 *
 * Grip sends no invoices and cannot see one being sent. A month counts as
 * invoiced only after someone recorded the number, the date and the amount
 * here; until then the screen says "aangeleverd" and no more.
 */
export function BillingSection({ assignmentId }: { assignmentId: string }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: billingKey(assignmentId),
    queryFn: () => fetchBillingStatus(assignmentId),
  });
  const status = query.data;
  const months = status?.months ?? [];
  const invoices = status?.invoices ?? [];
  const mayRecord = Boolean(status?.may_record_invoice);

  const [chosen, setChosen] = useState<string[]>([]);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [number, setNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState('');
  // Undefined until the person types: the field then shows what was delivered.
  const [amount, setAmount] = useState<string | undefined>(undefined);
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');

  // Only deliveries that are in force and carry no invoice can be chosen.
  const open = months.filter((m) => m.state === 'delivered' && m.export_id);
  const selection = open.filter((m) => m.export_id && chosen.includes(m.export_id));
  const exportIds = selection.map((m) => m.export_id as string);

  const proposal = useQuery({
    queryKey: [...billingKey(assignmentId), 'proposal', ...exportIds],
    queryFn: () => fetchInvoiceProposal(assignmentId, exportIds),
    enabled: dialog?.kind === 'record' && exportIds.length > 0,
  });

  const run = useMutation({
    mutationFn: (action: () => Promise<BillingStatus>) => action(),
    onSuccess: async (updated) => {
      queryClient.setQueryData(billingKey(assignmentId), updated);
      setDialog(null);
      setFormError(null);
      setChosen([]);
      await queryClient.invalidateQueries({ queryKey: ['assignments'] });
      await queryClient.invalidateQueries({ queryKey: ['reports'] });
    },
    onError: (failure) => setFormError(errorMessage(failure)),
  });

  const openDialog = (next: Dialog) => {
    setFormError(null);
    setNotice(null);
    if (next?.kind === 'record') {
      setNumber('');
      setInvoiceDate('');
      setAmount(undefined);
      setNote('');
    }
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

  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  if (!status) return null;
  // Someone who may not read the financial data gets no amounts and no months.
  if (status.delivered_cents === undefined) return null;

  const inForce = invoices.filter((invoice) => !invoice.withdrawn_at);
  const withdrawn = invoices.filter((invoice) => invoice.withdrawn_at);
  const correcting = dialog?.kind === 'correct' ? dialog.invoice : null;
  const withdrawing = dialog?.kind === 'withdraw' ? dialog.invoice : null;

  return (
    <nldd-simple-section>
      <SectionHeading text="Aanleveren en factureren" />
      <nldd-container gap="16">
        <nldd-text>
          Grip verstuurt geen facturen. Aangeleverd betekent dat de factuurgegevens van een
          afgesloten maand zijn geëxporteerd voor de financiële administratie. Een maand telt
          pas als gefactureerd wanneer hier is vastgelegd dat de factuur is verstuurd, met
          nummer, datum en bedrag.
        </nldd-text>
        {!status.billable ? (
          <nldd-banner
            variant="neutral"
            size="sm"
            text="Voor deze opdracht kunnen nog geen factuurgegevens worden aangeleverd"
            supporting-text="Dat kan zodra de offerte formeel is geaccepteerd."
          />
        ) : null}
        {notice ? <nldd-banner variant="success" size="sm" text={notice} /> : null}
        <Totals status={status} />

        {months.length === 0 ? (
          <EmptyNotice
            text="Er is nog geen maand afgesloten"
            supportingText="Na het afsluiten van een maand kun je de factuurgegevens aanleveren."
          />
        ) : (
          <nldd-table
            accessible-label="Aanlevering en factuur per afgesloten maand"
            columns={
              mayRecord
                ? 'minmax(120px,1fr) minmax(240px,2.4fr) minmax(110px,1fr) minmax(110px,1fr) 70px'
                : 'minmax(120px,1fr) minmax(240px,2.4fr) minmax(110px,1fr) minmax(110px,1fr)'
            }
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Maand" />
              <nldd-text-cell text="Stand" />
              <nldd-text-cell text="Aangeleverd" horizontal-alignment="right" />
              <nldd-text-cell text="Gefactureerd" horizontal-alignment="right" />
              {mayRecord ? <nldd-text-cell text="Kies" /> : null}
            </nldd-table-row>
            {months.map((month) => {
              const remark = billingStateRemark(month);
              const exportId = month.state === 'delivered' ? month.export_id : null;
              return (
                <nldd-table-row key={month.month}>
                  <nldd-cell>
                    <nldd-container gap="4">
                      <nldd-text>{formatMonth(month.month)}</nldd-text>
                      <nldd-badge
                        size="sm"
                        color={STATE_COLORS[month.state]}
                        text={STATE_LABELS[month.state]}
                      />
                    </nldd-container>
                  </nldd-cell>
                  <nldd-text-cell
                    text={billingStateText(month)}
                    {...(remark ? { 'supporting-text': remark, color: 'warning' } : {})}
                  />
                  <nldd-text-cell
                    text={month.delivered_cents === null ? '' : formatEuro(month.delivered_cents)}
                    horizontal-alignment="right"
                  />
                  <nldd-text-cell
                    text={month.invoiced_cents === null ? '' : formatEuro(month.invoiced_cents)}
                    horizontal-alignment="right"
                  />
                  {mayRecord && exportId ? (
                    <ChooseCell
                      label={`Kies ${formatMonth(month.month)} voor een factuur`}
                      checked={chosen.includes(exportId)}
                      onChange={(checked) =>
                        setChosen((current) =>
                          checked
                            ? [...current.filter((id) => id !== exportId), exportId]
                            : current.filter((id) => id !== exportId),
                        )
                      }
                    />
                  ) : null}
                  {mayRecord && !exportId ? <nldd-text-cell text="" /> : null}
                </nldd-table-row>
              );
            })}
          </nldd-table>
        )}

        {mayRecord && open.length > 0 ? (
          <>
            <nldd-text size="sm">
              Kies de aangeleverde maanden waarvoor een factuur is verstuurd. Een factuur mag
              meerdere maanden beslaan.
            </nldd-text>
            <nldd-button-group>
              <Button
                text="Leg factuur vast"
                appearance="primary"
                disabled={exportIds.length === 0}
                onClick={() => openDialog({ kind: 'record' })}
              />
            </nldd-button-group>
          </>
        ) : null}

        <SectionHeading text="Vastgelegde facturen" level={3} />
        {inForce.length === 0 ? (
          <EmptyNotice
            text="Er is nog geen factuur vastgelegd"
            supportingText="Tot die tijd telt geen enkel bedrag van deze opdracht als gefactureerd."
          />
        ) : (
          <nldd-table
            accessible-label="Vastgelegde facturen"
            columns={
              mayRecord
                ? 'minmax(120px,1fr) minmax(110px,1fr) minmax(160px,1.4fr) minmax(110px,1fr) minmax(200px,1.8fr) 210px'
                : 'minmax(120px,1fr) minmax(110px,1fr) minmax(160px,1.4fr) minmax(110px,1fr) minmax(200px,1.8fr)'
            }
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Factuurnummer" />
              <nldd-text-cell text="Factuurdatum" />
              <nldd-text-cell text="Maanden" />
              <nldd-text-cell text="Factuurbedrag" horizontal-alignment="right" />
              <nldd-text-cell text="Vergeleken met aangeleverd" />
              {mayRecord ? <nldd-text-cell text="Actie" /> : null}
            </nldd-table-row>
            {inForce.map((invoice) => (
              <nldd-table-row key={invoice.id}>
                <nldd-text-cell
                  text={invoice.invoice_number}
                  supporting-text={
                    invoice.source === 'financial_system'
                      ? 'Uit het financiële systeem'
                      : `Vastgelegd door ${invoice.recorded_by_name ?? 'onbekend'} op ${formatDateTime(invoice.recorded_at)}`
                  }
                />
                <nldd-text-cell text={formatDate(invoice.invoice_date)} />
                <nldd-text-cell text={monthsText(invoice.months)} />
                <nldd-text-cell
                  text={formatEuro(invoice.amount_cents)}
                  horizontal-alignment="right"
                />
                <nldd-text-cell
                  text={differenceText(invoice)}
                  supporting-text={`Aangeleverd: ${formatEuro(invoice.delivered_cents)}`}
                  {...(invoice.difference_cents !== 0 ? { color: 'warning' } : {})}
                />
                {mayRecord ? (
                  <nldd-cell>
                    <nldd-button-group>
                      <Button
                        size="sm"
                        text="Corrigeer"
                        accessibleLabel={`Corrigeer factuur ${invoice.invoice_number}`}
                        onClick={() => openDialog({ kind: 'correct', invoice })}
                      />
                      <Button
                        size="sm"
                        text="Trek in"
                        accessibleLabel={`Trek factuur ${invoice.invoice_number} in`}
                        onClick={() => openDialog({ kind: 'withdraw', invoice })}
                      />
                    </nldd-button-group>
                  </nldd-cell>
                ) : null}
              </nldd-table-row>
            ))}
          </nldd-table>
        )}

        {withdrawn.length > 0 ? (
          <>
            <SectionHeading text="Ingetrokken" level={3} />
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
          </>
        ) : null}
      </nldd-container>

      <FormSheet
        open={dialog?.kind === 'record'}
        title="Factuur vastleggen"
        submitText="Leg vast"
        busy={run.isPending}
        error={dialog?.kind === 'record' ? formError : null}
        onClose={() => setDialog(null)}
        onSubmit={() => {
          const input = fields();
          if (!input) return;
          run.mutate(() => recordInvoice(assignmentId, { ...input, export_ids: exportIds }), {
            onSuccess: () => setNotice(`Factuur ${input.invoice_number} is vastgelegd.`),
          });
        }}
      >
        <nldd-text>
          Hiermee leg je vast dat er een factuur is verstuurd voor{' '}
          {monthsText(selection.map((m) => m.month))}. Grip verstuurt de factuur niet en
          controleert niet of die bestaat.
        </nldd-text>
        <nldd-text size="sm">
          {proposal.data
            ? `Voor deze maanden is ${formatEuro(proposal.data.delivered_cents)} aangeleverd. Wijkt het factuurbedrag af, dan blijft het verschil zichtbaar.`
            : 'Het aangeleverde bedrag wordt opgehaald.'}
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
        open={dialog?.kind === 'correct'}
        title="Factuur corrigeren"
        submitText="Bewaar correctie"
        busy={run.isPending}
        error={dialog?.kind === 'correct' ? formError : null}
        onClose={() => setDialog(null)}
        onSubmit={() => {
          if (!correcting) return;
          const input = fields();
          if (!input) return;
          run.mutate(() => correctInvoice(correcting.id, input), {
            onSuccess: () => setNotice(`Factuur ${input.invoice_number} is gecorrigeerd.`),
          });
        }}
      >
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
        onClose={() => setDialog(null)}
        onSubmit={() => {
          if (!withdrawing) return;
          if (!reason.trim()) {
            setFormError('Geef een reden voor het intrekken.');
            return;
          }
          run.mutate(() => withdrawInvoice(withdrawing.id, reason.trim()), {
            onSuccess: () =>
              setNotice(`Factuur ${withdrawing.invoice_number} is ingetrokken.`),
          });
        }}
      >
        <nldd-text>
          Intrekken is voor een factuur die hier ten onrechte is vastgelegd. De maanden
          staan daarna weer als aangeleverd, niet als gefactureerd. De vastlegging en de reden
          blijven bewaard.
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} required multiline />
      </FormSheet>
    </nldd-simple-section>
  );
}
