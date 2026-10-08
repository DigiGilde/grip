import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import {
  Button,
  DateInput,
  EmptyNotice,
  ErrorNotice,
  FormSheet,
  Loading,
  SectionHeading,
  TextInput,
} from '@/features/assignments/ui';
import { useInstance } from '@/layout/useInstance';
import { formatDate, formatEuro } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import {
  ACCEPTANCE_FORM_LABELS,
  QUOTE_STATUS_COLORS,
  QUOTE_STATUS_LABELS,
  fetchInvitations,
  fetchQuotePreview,
  fetchQuotes,
  inviteSigner,
  issueQuote,
  quoteDocumentUrl,
  quoteKeys,
  recordRejection,
  recordUploadedAcceptance,
  signedDocumentUrl,
  signingLink,
  type QuotePreview,
  type QuoteSummary,
} from './api';
import { QuoteContentTable } from './QuoteContentTable';
import { DocumentLink, FileInput } from './ui';
import { formatDateTime, shortHash } from './format';

type Dialog =
  | { kind: 'issue' }
  | { kind: 'invite'; quote: QuoteSummary }
  | { kind: 'upload'; quote: QuoteSummary }
  | { kind: 'reject'; quote: QuoteSummary }
  | null;

function differenceText(preview: QuotePreview): string | null {
  const difference = preview.difference_cents;
  if (difference === null || difference === undefined) return null;
  if (difference === 0) return 'Het afgesproken bedrag is gelijk aan de begroting.';
  const amount = formatEuro(Math.abs(difference));
  return difference > 0
    ? `Het afgesproken bedrag is ${amount} hoger dan de begroting.`
    : `Het afgesproken bedrag is ${amount} lager dan de begroting.`;
}

function Invitations({ quoteId }: { quoteId: string }) {
  const query = useQuery({
    queryKey: quoteKeys.invitations(quoteId),
    queryFn: () => fetchInvitations(quoteId),
  });
  const invitations = query.data?.invitations ?? [];
  if (query.isPending || invitations.length === 0) return null;
  return (
    <nldd-table
      accessible-label="Uitnodigingen om te tekenen"
      columns="minmax(200px,2fr) minmax(140px,1fr) minmax(140px,1fr)"
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Uitgenodigd" />
        <nldd-text-cell text="Op" />
        <nldd-text-cell text="Getekend" />
      </nldd-table-row>
      {invitations.map((invitation) => (
        <nldd-table-row key={invitation.id}>
          <nldd-text-cell text={invitation.email} />
          <nldd-text-cell text={formatDateTime(invitation.created_at)} />
          <nldd-text-cell
            text={invitation.used_at ? formatDateTime(invitation.used_at) : 'Nog niet'}
          />
        </nldd-table-row>
      ))}
    </nldd-table>
  );
}

function QuoteCard({
  quote,
  mayManage,
  onOpen,
}: {
  quote: QuoteSummary;
  mayManage: boolean;
  onOpen: (dialog: Dialog) => void;
}) {
  const open = quote.status === 'issued';
  const acceptance = quote.acceptance ?? null;
  const rejection = quote.rejection ?? null;
  const facts = [
    quote.issued_by_name ? `Uitgegeven door ${quote.issued_by_name}` : null,
    quote.valid_until ? `Geldig tot en met ${formatDate(quote.valid_until)}` : null,
    quote.snapshot_hash ? `Controlegetal ${shortHash(quote.snapshot_hash)}` : null,
  ].filter(Boolean);

  return (
    <nldd-container gap="8">
      <nldd-title
        size={4}
        heading-level={3}
        text={`Offerte van ${formatDateTime(quote.issued_at)}`}
        {...(quote.total_cents !== undefined
          ? { 'supporting-text': formatEuro(quote.total_cents) }
          : {})}
      >
        <nldd-badge
          slot="end"
          color={QUOTE_STATUS_COLORS[quote.status] ?? 'neutral'}
          text={QUOTE_STATUS_LABELS[quote.status] ?? quote.status}
        />
      </nldd-title>
      {facts.length > 0 ? <nldd-text size="sm">{facts.join('. ')}.</nldd-text> : null}

      {acceptance ? (
        <nldd-text>
          {ACCEPTANCE_FORM_LABELS[acceptance.form] ?? 'Akkoord vastgelegd'} op{' '}
          {formatDateTime(acceptance.signed_at)}
          {acceptance.signer_name ? `, door ${acceptance.signer_name}` : ''}
          {acceptance.signer_function ? ` (${acceptance.signer_function})` : ''}
          {acceptance.organisation_name ? `, namens ${acceptance.organisation_name}` : ''}.
        </nldd-text>
      ) : null}
      {rejection ? (
        <nldd-text>
          Afgewezen op {formatDateTime(rejection.rejected_at)}
          {rejection.reason ? `. Reden: ${rejection.reason}` : '.'}
        </nldd-text>
      ) : null}

      {quote.snapshot_hash !== undefined ? (
        <nldd-container layout="wrap" gap="16">
          <DocumentLink href={quoteDocumentUrl(quote.id)} text="Bekijk de offerte" newTab />
          <DocumentLink href={quoteDocumentUrl(quote.id, true)} text="Download de offerte" />
          {acceptance?.has_document ? (
            <DocumentLink href={signedDocumentUrl(quote.id)} text="Download het getekende exemplaar" />
          ) : null}
        </nldd-container>
      ) : null}

      {mayManage && open ? (
        <>
          <nldd-button-group>
            <Button
              text="Nodig ondertekenaar uit"
              onClick={() => onOpen({ kind: 'invite', quote })}
            />
            <Button
              text="Leg getekende pdf vast"
              onClick={() => onOpen({ kind: 'upload', quote })}
            />
            <Button text="Leg afwijzing vast" onClick={() => onOpen({ kind: 'reject', quote })} />
          </nldd-button-group>
          <Invitations quoteId={quote.id} />
        </>
      ) : null}
      {mayManage && !open && quote.status !== 'superseded' ? (
        <Invitations quoteId={quote.id} />
      ) : null}
    </nldd-container>
  );
}

/** The quote of an assignment: what it would say now, and what was issued. */
export function QuotePage() {
  const { assignmentId = '' } = useParams();
  const instance = useInstance();
  const queryClient = useQueryClient();
  const preview = useQuery({
    queryKey: quoteKeys.preview(assignmentId),
    queryFn: () => fetchQuotePreview(assignmentId),
  });
  const list = useQuery({
    queryKey: quoteKeys.list(assignmentId),
    queryFn: () => fetchQuotes(assignmentId),
  });

  const [dialog, setDialog] = useState<Dialog>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [validUntil, setValidUntil] = useState('');
  const [conditions, setConditions] = useState('');
  const [email, setEmail] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [signerName, setSignerName] = useState('');
  const [signerEmail, setSignerEmail] = useState('');
  const [signerFunction, setSignerFunction] = useState('');
  const [organisationName, setOrganisationName] = useState('');
  const [signedAt, setSignedAt] = useState('');
  const [reason, setReason] = useState('');

  const open = (next: Dialog) => {
    setFormError(null);
    setDialog(next);
  };
  const close = () => setDialog(null);

  const run = useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    onSuccess: async () => {
      setDialog(null);
      setFormError(null);
      await queryClient.invalidateQueries({ queryKey: ['quotes'] });
      await queryClient.invalidateQueries({ queryKey: ['assignments'] });
    },
    onError: (error) => setFormError(errorMessage(error)),
  });

  const submit = (action: () => Promise<unknown>, done: string) =>
    run.mutate(action, { onSuccess: () => setNotice(done) });

  const data = preview.data;
  const title = data ? `Offerte ${data.assignment_name}` : 'Offerte';
  const difference = data ? differenceText(data) : null;
  const quotes = list.data?.quotes ?? [];
  const mayManage = list.data?.may_manage ?? false;
  const inviting = dialog?.kind === 'invite' ? dialog.quote : null;

  return (
    <>
      <nldd-simple-section>
        <PageHeading text={title} instanceName={instance?.name} />
        <nldd-link href={`/opdrachten/${assignmentId}`} text="Terug naar de opdracht" size="md" />

        {preview.isPending ? <Loading /> : null}
        {preview.isError ? <ErrorNotice message={errorMessage(preview.error)} /> : null}
        {notice ? <nldd-banner variant="success" size="sm" text={notice} /> : null}

        {data ? (
          <nldd-container gap="16">
            <SectionHeading text="Offerte op basis van de begroting" />
            {data.problem ? (
              <nldd-banner
                variant="warning"
                text="De offerte kan nog niet worden opgesteld"
                supporting-text={data.problem}
              />
            ) : null}
            {data.content ? (
              <>
                <QuoteContentTable
                  content={data.content}
                  label="Regels van de offerte op basis van de begroting"
                />
                {data.quoted_amount_cents !== null && data.quoted_amount_cents !== undefined ? (
                  <nldd-text>
                    Afgesproken bedrag: {formatEuro(data.quoted_amount_cents)}. {difference}
                  </nldd-text>
                ) : null}
              </>
            ) : null}
            {!data.content && !data.problem ? (
              <EmptyNotice
                text="Je ziet de bedragen van deze offerte niet"
                supportingText="De inhoud van een offerte is zichtbaar voor wie de opdracht beheert."
              />
            ) : null}
            {data.may_issue && data.can_issue ? (
              <nldd-button-group>
                <Button
                  text="Geef offerte uit"
                  appearance="primary"
                  onClick={() => open({ kind: 'issue' })}
                />
              </nldd-button-group>
            ) : null}
            {data.may_issue && !data.can_issue && !data.problem ? (
              <nldd-text size="sm">
                In de huidige status van de opdracht kan geen nieuwe offerte worden uitgegeven.
              </nldd-text>
            ) : null}
          </nldd-container>
        ) : null}
      </nldd-simple-section>

      <nldd-simple-section>
        <SectionHeading text="Uitgegeven offertes" />
        {list.isPending ? <Loading /> : null}
        {list.isError ? <ErrorNotice message={errorMessage(list.error)} /> : null}
        {list.data && quotes.length === 0 ? (
          <EmptyNotice
            text="Er is nog geen offerte uitgegeven"
            supportingText="Een uitgegeven offerte verandert daarna niet meer, ook niet als tarieven of de begroting wijzigen."
          />
        ) : null}
        <nldd-container gap="32">
          {quotes.map((quote) => (
            <QuoteCard key={quote.id} quote={quote} mayManage={mayManage} onOpen={open} />
          ))}
        </nldd-container>
      </nldd-simple-section>

      <FormSheet
        open={dialog?.kind === 'issue'}
        title="Offerte uitgeven"
        submitText="Geef uit"
        busy={run.isPending}
        error={dialog?.kind === 'issue' ? formError : null}
        onClose={close}
        onSubmit={() =>
          submit(
            () =>
              issueQuote(assignmentId, {
                valid_until: validUntil || null,
                conditions: conditions.trim() || null,
              }),
            'De offerte is uitgegeven.',
          )
        }
      >
        <nldd-text>
          De offerte legt de begroting vast zoals die nu is. Een eerdere offerte die nog open
          staat, wordt vervangen.
        </nldd-text>
        <DateInput label="Geldig tot en met" value={validUntil} onChange={setValidUntil} optional />
        <TextInput
          label="Voorwaarden"
          value={conditions}
          onChange={setConditions}
          optional
          multiline
        />
      </FormSheet>

      <FormSheet
        open={dialog?.kind === 'invite'}
        title="Ondertekenaar uitnodigen"
        submitText="Nodig uit"
        busy={run.isPending}
        error={dialog?.kind === 'invite' ? formError : null}
        onClose={close}
        onSubmit={() => {
          if (!inviting) return;
          submit(
            () => inviteSigner(inviting.id, email.trim()),
            `De uitnodiging staat klaar. Stuur de ondertekenaar deze link: ${signingLink(inviting.id)}`,
          );
        }}
      >
        <nldd-text>
          De uitgenodigde persoon logt in met SSO Rijk en ziet alleen deze offerte. Grip
          verstuurt zelf geen e-mail: je stuurt de link na het uitnodigen zelf door.
        </nldd-text>
        <TextInput
          label="E-mailadres van de ondertekenaar"
          hint="Het adres waarmee deze persoon inlogt"
          value={email}
          onChange={setEmail}
          required
        />
      </FormSheet>

      <FormSheet
        open={dialog?.kind === 'upload'}
        title="Getekende pdf vastleggen"
        submitText="Leg akkoord vast"
        busy={run.isPending}
        error={dialog?.kind === 'upload' ? formError : null}
        onClose={close}
        onSubmit={() => {
          if (dialog?.kind !== 'upload') return;
          if (!file) {
            setFormError('Kies het getekende pdf-bestand.');
            return;
          }
          const quote = dialog.quote;
          submit(
            () =>
              recordUploadedAcceptance(quote.id, {
                file,
                signer_name: signerName.trim(),
                signer_email: signerEmail.trim(),
                signer_function: signerFunction.trim(),
                organisation_name: organisationName.trim(),
                signed_at: signedAt,
              }),
            'Het akkoord is vastgelegd.',
          );
        }}
      >
        <nldd-text>
          Hiermee leg je vast dat de opdrachtgever deze offerte heeft getekend. Dit is niet
          terug te draaien.
        </nldd-text>
        <FileInput
          label="Getekende offerte"
          hint="Een pdf van hooguit 10 MB"
          accept=".pdf,application/pdf"
          onChange={setFile}
        />
        <TextInput label="Naam van wie tekende" value={signerName} onChange={setSignerName} required />
        <TextInput
          label="E-mailadres van wie tekende"
          value={signerEmail}
          onChange={setSignerEmail}
          required
        />
        <TextInput label="Functie" value={signerFunction} onChange={setSignerFunction} optional />
        <TextInput
          label="Organisatie"
          hint="Alleen nodig als de opdracht geen opdrachtgever noemt"
          value={organisationName}
          onChange={setOrganisationName}
          optional
        />
        <DateInput label="Datum van tekenen" value={signedAt} onChange={setSignedAt} optional />
      </FormSheet>

      <FormSheet
        open={dialog?.kind === 'reject'}
        title="Afwijzing vastleggen"
        submitText="Leg afwijzing vast"
        busy={run.isPending}
        error={dialog?.kind === 'reject' ? formError : null}
        onClose={close}
        onSubmit={() => {
          if (dialog?.kind !== 'reject') return;
          const quote = dialog.quote;
          submit(
            () => recordRejection(quote.id, reason.trim() || null),
            'De afwijzing is vastgelegd.',
          );
        }}
      >
        <nldd-text>
          Hiermee leg je vast dat de opdrachtgever deze offerte heeft afgewezen. De opdracht
          krijgt de status afgewezen; een nieuwe offerte uitgeven kan daarna weer.
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} optional multiline />
      </FormSheet>
    </>
  );
}
