import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { centsToInput, parseEuroToCents } from '@/features/assignments/money';
import { DateInput, SelectInput, TextInput } from '@/features/assignments/ui';
import { CheckboxInput } from '@/features/quotes/ui';
import { formatEuro } from '@/lib/format';
import { Facts, FormSheet, Quiet, Stack } from '@/ui/layout';
import {
  deliverPeriod,
  recordPeriodInvoice,
  saveTerms,
  type BillingDetails,
  type BillingOverview,
  type BillingPeriod,
  type DetailKey,
  type Rhythm,
} from './billingApi';
import { DETAIL_LABELS, periodName } from './periodText';

const ADDRESS_KEYS: DetailKey[] = [
  'organisation',
  'attention_of',
  'address',
  'postcode_city',
  'reference',
];
const CONTACT_KEYS: DetailKey[] = ['contact_name', 'contact_phone', 'contact_email'];
const REQUIRED: DetailKey[] = ['organisation', 'address', 'postcode_city'];

function useRefresh(assignmentId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: ['months', assignmentId] });
    await queryClient.invalidateQueries({ queryKey: ['billing'] });
    await queryClient.invalidateQueries({ queryKey: ['assignments'] });
    await queryClient.invalidateQueries({ queryKey: ['tasks'] });
  };
}

function DetailFields({
  keys,
  details,
  onChange,
}: {
  keys: DetailKey[];
  details: BillingDetails;
  onChange: (key: DetailKey, value: string) => void;
}) {
  return (
    <>
      {keys.map((key) => (
        <TextInput
          key={key}
          label={DETAIL_LABELS[key]}
          value={details[key] ?? ''}
          onChange={(value) => onChange(key, value)}
          {...(REQUIRED.includes(key) ? { required: true } : { optional: true })}
          {...(key === 'reference'
            ? { hint: 'Een verplichtingennummer of ordernummer van de opdrachtgever' }
            : {})}
        />
      ))}
    </>
  );
}

function missing(details: BillingDetails): DetailKey | null {
  return REQUIRED.find((key) => !(details[key] ?? '').trim()) ?? null;
}

interface TermsSheetProps {
  overview: BillingOverview;
  open: boolean;
  onClose: () => void;
}

/** How the assignment is billed and where the invoice goes. */
export function TermsSheet({ overview, open, onClose }: TermsSheetProps) {
  const refresh = useRefresh(overview.assignment_id);
  const [rhythm, setRhythm] = useState<Rhythm>(overview.terms.rhythm);
  const [details, setDetails] = useState<BillingDetails>(overview.terms.details ?? {});
  const [names, setNames] = useState(Boolean(overview.terms.names_on_specification));
  const [error, setError] = useState<string | null>(null);
  // The sheet stays in the page; each opening starts from what is recorded.
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setRhythm(overview.terms.rhythm);
      setDetails(overview.terms.details ?? {});
      setNames(Boolean(overview.terms.names_on_specification));
      setError(null);
    }
  }
  const delivered = overview.periods.some((period) => (period.deliveries ?? []).length > 0);
  const save = useMutation({
    mutationFn: () =>
      saveTerms(overview.assignment_id, {
        ...(delivered ? {} : { rhythm }),
        details,
        names_on_specification: names,
      }),
    onSuccess: async () => {
      await refresh();
      onClose();
    },
    onError: (failure) => setError(errorMessage(failure)),
  });
  return (
    <FormSheet
      open={open}
      title="Factuurafspraken"
      submitText="Bewaar"
      busy={save.isPending}
      error={error}
      onClose={onClose}
      onSubmit={() => {
        setError(null);
        save.mutate();
      }}
    >
      <SelectInput
        label="Factureren"
        value={rhythm}
        onChange={(value) => setRhythm(value as Rhythm)}
        options={[
          { value: 'quarter', label: 'Per kwartaal' },
          { value: 'month', label: 'Per maand' },
        ]}
        disabled={delivered}
        {...(delivered ? { hint: 'Ligt vast: er is al een periode aangeleverd' } : {})}
      />
      <nldd-title size={5} heading-level={2} text="Factuur aan" />
      <DetailFields
        keys={ADDRESS_KEYS}
        details={details}
        onChange={(key, value) => setDetails((current) => ({ ...current, [key]: value }))}
      />
      <nldd-title size={5} heading-level={2} text="Contact bij de financiële afdeling" />
      <DetailFields
        keys={CONTACT_KEYS}
        details={details}
        onChange={(key, value) => setDetails((current) => ({ ...current, [key]: value }))}
      />
      <CheckboxInput
        label="Noem de mensen bij naam op de specificatie"
        checked={names}
        onChange={setNames}
      />
    </FormSheet>
  );
}

interface DeliverSheetProps {
  overview: BillingOverview;
  period: BillingPeriod | null;
  onClose: () => void;
}

/**
 * Hand a period to the financial administration. Says what goes, to whom
 * and where the invoice must go; asks for the invoice address only when it
 * is not known yet.
 */
export function DeliverSheet({ overview, period, onClose }: DeliverSheetProps) {
  const refresh = useRefresh(overview.assignment_id);
  const [last, setLast] = useState<BillingPeriod | null>(period);
  const [details, setDetails] = useState<BillingDetails>(overview.terms.details ?? {});
  const [via, setVia] = useState<'mail' | 'self'>(overview.can_mail ? 'mail' : 'self');
  const [error, setError] = useState<string | null>(null);
  if (period !== null && period !== last) {
    setLast(period);
    setDetails(overview.terms.details ?? {});
    setVia(overview.can_mail ? 'mail' : 'self');
    setError(null);
  }
  const shown = period ?? last;
  const asked = (overview.terms.missing_details ?? []).length > 0;

  const deliver = useMutation({
    mutationFn: async () => {
      if (!shown) return;
      if (asked) await saveTerms(overview.assignment_id, { details });
      await deliverPeriod(overview.assignment_id, shown.key, via);
    },
    onSuccess: async () => {
      await refresh();
      onClose();
    },
    onError: async (failure) => {
      setError(errorMessage(failure));
      await refresh();
    },
  });

  const known = overview.terms.details ?? {};
  const months = shown?.months ?? [];
  const corrections = months.filter((month) => (month.correction_cents ?? 0) !== 0);
  return (
    <FormSheet
      open={period !== null}
      title={
        shown
          ? shown.correction
            ? `Lever de naverrekening over ${periodName(shown.label)} aan`
            : `Lever ${periodName(shown.label)} aan`
          : 'Lever aan'
      }
      submitText={
        shown?.to_deliver_cents !== null && shown?.to_deliver_cents !== undefined
          ? `Lever ${formatEuro(shown.to_deliver_cents)} aan`
          : 'Lever aan'
      }
      busy={deliver.isPending}
      error={error}
      onClose={onClose}
      onSubmit={() => {
        setError(null);
        if (asked) {
          const gap = missing(details);
          if (gap) {
            setError(`Vul in: ${DETAIL_LABELS[gap].toLowerCase()}.`);
            return;
          }
        }
        deliver.mutate();
      }}
    >
      <Stack gap="close">
        <nldd-text>
          Grip maakt een factuurverzoek: één document met het bedrag, de specificatie per maand en
          het factuuradres. Daarmee maakt de financiële administratie de factuur.
        </nldd-text>
        {corrections.length > 0 ? (
          <Quiet>
            Hierin zit een naverrekening over {corrections.map((month) => month.label).join(' en ')}
            : de prijs is na de aanlevering gewijzigd.
          </Quiet>
        ) : null}
      </Stack>
      {asked ? (
        <>
          <nldd-title size={5} heading-level={2} text="Waar gaat de factuur heen?" />
          <DetailFields
            keys={ADDRESS_KEYS}
            details={details}
            onChange={(key, value) => setDetails((current) => ({ ...current, [key]: value }))}
          />
        </>
      ) : (
        <Facts
          label="Factuur aan"
          labelWidth="160px"
          facts={ADDRESS_KEYS.filter((key) => known[key]).map((key) => ({
            label: DETAIL_LABELS[key],
            value: known[key],
          }))}
        />
      )}
      {overview.can_mail && overview.recipient ? (
        <SelectInput
          label="Hoe lever je aan"
          value={via}
          onChange={(value) => setVia(value === 'self' ? 'self' : 'mail')}
          options={[
            { value: 'mail', label: `Mail aan ${overview.recipient}` },
            { value: 'self', label: 'Ik geef het factuurverzoek zelf door' },
          ]}
        />
      ) : null}
    </FormSheet>
  );
}

interface InvoiceSheetProps {
  overview: BillingOverview;
  period: BillingPeriod | null;
  onClose: () => void;
}

function today(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Record the invoice that was sent for a delivered period. */
export function PeriodInvoiceSheet({ overview, period, onClose }: InvoiceSheetProps) {
  const refresh = useRefresh(overview.assignment_id);
  const [last, setLast] = useState<BillingPeriod | null>(period);
  const open = (target: BillingPeriod | null) =>
    target ? centsToInput((target.delivered_cents ?? 0) - (target.invoiced_cents ?? 0)) : '';
  const [number, setNumber] = useState('');
  const [date, setDate] = useState(today());
  const [amount, setAmount] = useState(open(period));
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  if (period !== null && period !== last) {
    setLast(period);
    setNumber('');
    setDate(today());
    setAmount(open(period));
    setNote('');
    setError(null);
  }
  const shown = period ?? last;
  const record = useMutation({
    mutationFn: (cents: number) =>
      recordPeriodInvoice(overview.assignment_id, shown?.key ?? '', {
        invoice_number: number.trim(),
        invoice_date: date,
        amount_cents: cents,
        note: note.trim() || null,
      }),
    onSuccess: async () => {
      await refresh();
      onClose();
    },
    onError: (failure) => setError(errorMessage(failure)),
  });
  return (
    <FormSheet
      open={period !== null}
      title={shown ? `Factuur over ${periodName(shown.label)}` : 'Factuur'}
      submitText="Leg de factuur vast"
      busy={record.isPending}
      error={error}
      onClose={onClose}
      onSubmit={() => {
        setError(null);
        if (!number.trim()) {
          setError('Vul het factuurnummer in.');
          return;
        }
        const cents = parseEuroToCents(amount);
        if (cents === null) {
          setError('Het bedrag is een getal in euro, bijvoorbeeld 22.500,00.');
          return;
        }
        record.mutate(cents);
      }}
    >
      <TextInput label="Factuurnummer" value={number} onChange={setNumber} required />
      <DateInput label="Factuurdatum" value={date} onChange={setDate} required />
      <TextInput
        label="Bedrag op de factuur"
        value={amount}
        onChange={setAmount}
        required
        hint={
          shown
            ? `Aangeleverd is ${formatEuro((shown.delivered_cents ?? 0) - (shown.invoiced_cents ?? 0))}`
            : undefined
        }
      />
      <TextInput label="Opmerking" value={note} onChange={setNote} optional multiline />
    </FormSheet>
  );
}
