import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { useAuth } from '@/auth/context';
import { PATHS } from '@/paths';
import { Button, DateInput, TextInput } from '@/features/assignments/ui';
import { useAssignmentShell } from '@/features/assignments/shell';
import { useInstance } from '@/layout/useInstance';
import { formatEuro } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { EmptyNotice, ErrorNotice, FormSheet, Loading, Quiet, Section, Stack } from '@/ui/layout';
import {
  fetchQuoteDetail,
  fetchQuotePreview,
  fetchQuotes,
  issueQuote,
  offerQuote,
  quoteKeys,
  recordRejection,
  recordUploadedAcceptance,
  renewInvitation,
  withdrawInvitation,
  type OfferChannel,
  type QuotePreview,
  type QuoteSummary,
} from './api';
import {
  approvalKeys,
  approvalPath,
  fetchApprovals,
  requestApproval,
  withdrawApproval,
} from './approval';
import { OfferSheet } from './OfferSheet';
import { EarlierQuoteRow, QuoteCard, type CardAction } from './QuoteCard';
import { QuoteContentTable } from './QuoteContentTable';
import { partMonthNote, rateChangeNote } from './format';
import { FileInput } from './ui';

type Dialog = 'issue' | 'offer' | 'upload' | 'reject' | 'approval' | null;

function differenceText(preview: QuotePreview): string | null {
  const difference = preview.difference_cents;
  if (difference === null || difference === undefined || difference === 0) return null;
  const amount = formatEuro(Math.abs(difference));
  return difference > 0
    ? `Afgesproken is ${formatEuro(preview.quoted_amount_cents)}: ${amount} meer dan de begroting.`
    : `Afgesproken is ${formatEuro(preview.quoted_amount_cents)}: ${amount} minder dan de begroting.`;
}

/**
 * The quote of an assignment: where it stands and what to do next.
 *
 * The current quote is one card. A new quote from the budget is offered
 * above it only when there is none to wait for, or when the budget no longer
 * says what the quote says. Earlier quotes are one line each.
 */
export function QuotePage() {
  const { assignmentId = '' } = useParams();
  const shell = useAssignmentShell();
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
  const quotes = list.data?.quotes ?? [];
  const mayManage = list.data?.may_manage ?? false;
  // The quote the tab is about: the newest that was not replaced.
  const current: QuoteSummary | null =
    quotes.find((quote) => quote.status !== 'superseded') ?? null;
  const earlier = quotes.filter((quote) => quote.id !== current?.id);
  const detail = useQuery({
    queryKey: quoteKeys.detail(current?.id ?? ''),
    queryFn: () => fetchQuoteDetail(current?.id ?? ''),
    enabled: current !== null,
  });

  // Where the organisation approves quotes internally; elsewhere this says
  // "not required" for every quote and nothing of it shows.
  const approvals = useQuery({
    queryKey: approvalKeys.ofAssignment(assignmentId),
    queryFn: () => fetchApprovals(assignmentId),
    enabled: current !== null,
  });
  const approval = approvals.data?.items?.find((item) => item.quote_id === current?.id) ?? null;
  const navigate = useNavigate();
  const { state: auth } = useAuth();
  const isAdmin = auth.status === 'authenticated' && auth.functions.includes('beheerder');

  const [dialog, setDialog] = useState<Dialog>(null);
  const [approvalNote, setApprovalNote] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  const [validUntil, setValidUntil] = useState('');
  // Undefined until the person types: the field then shows the proposed text.
  const [conditions, setConditions] = useState<string | undefined>(undefined);
  const [clientReference, setClientReference] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [signerName, setSignerName] = useState('');
  const [signerEmail, setSignerEmail] = useState('');
  const [signerFunction, setSignerFunction] = useState('');
  const [organisationName, setOrganisationName] = useState('');
  const [signedAt, setSignedAt] = useState('');
  const [reason, setReason] = useState('');

  const open = (next: Dialog) => {
    setFormError(null);
    setPageError(null);
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
  });
  const submit = (action: () => Promise<unknown>) =>
    run.mutate(action, { onError: (error) => setFormError(errorMessage(error)) });
  /** An action without a sheet: a failure shows above the card. */
  const act = (action: () => Promise<unknown>) =>
    run.mutate(action, { onError: (error) => setPageError(errorMessage(error)) });

  const onCard = (action: CardAction) => {
    if (!current) return;
    if (action.kind === 'offer') open('offer');
    else if (action.kind === 'upload') open('upload');
    else if (action.kind === 'reject') open('reject');
    else if (action.kind === 'request-approval') open('approval');
    else if (action.kind === 'new-quote') open('issue');
    else if (action.kind === 'review') navigate(approvalPath(current.id));
    else if (action.kind === 'grant-right') navigate(PATHS.team);
    else if (action.kind === 'withdraw-approval') act(() => withdrawApproval(current.id));
    else if (action.kind === 'withdraw-link') {
      act(() => withdrawInvitation(current.id, action.invitationId));
    } else act(() => renewInvitation(current.id, action.invitationId));
  };

  const data = preview.data;
  const title = data ? `Offerte ${data.assignment_name}` : 'Offerte';
  const waiting = current?.status === 'issued';
  // A new quote is in order when none is out, or the budget moved since.
  const budgetMoved =
    waiting &&
    data?.content !== undefined &&
    current?.total_cents !== undefined &&
    data.content.total_cents !== current.total_cents;
  const canIssue = Boolean(data?.may_issue && data.can_issue);
  const showPreview = Boolean(data?.may_issue) && current?.status !== 'accepted' && !waiting;
  const difference = data ? differenceText(data) : null;
  const conditionsText = conditions ?? data?.default_conditions ?? '';
  const partMonth = data?.content
    ? [partMonthNote(data.content.lines), rateChangeNote(data.content.lines)]
        .filter(Boolean)
        .join(' ') || null
    : null;

  return (
    <>
      <nldd-simple-section>
        {/* Inside the tabs of an assignment the shell shows the name and the way back. */}
        {shell ? null : <PageHeading text={title} instanceName={instance?.name} />}
        <Stack gap="group">
          {list.isPending || preview.isPending ? <Loading /> : null}
          {list.isError ? <ErrorNotice message={errorMessage(list.error)} /> : null}
          {preview.isError ? <ErrorNotice message={errorMessage(preview.error)} /> : null}
          {pageError ? <ErrorNotice message={pageError} /> : null}

          {showPreview && data ? (
            <Section title="Nieuwe offerte" level={2}>
              {data.problem ? (
                <nldd-banner
                  variant="warning"
                  size="sm"
                  text="De offerte kan nog niet worden opgesteld"
                  supporting-text={data.problem}
                />
              ) : null}
              {data.content ? (
                <QuoteContentTable
                  content={data.content}
                  label="Regels van de nieuwe offerte, uit de begroting"
                />
              ) : null}
              {difference ? <Quiet>{difference}</Quiet> : null}
              {partMonth ? <Quiet>{partMonth}</Quiet> : null}
              {canIssue ? (
                <Stack gap="close">
                  <nldd-button-group>
                    <Button text="Maak offerte" appearance="primary" onClick={() => open('issue')} />
                  </nldd-button-group>
                  <Quiet>
                    Daarna wijzigt de offerte niet meer; voor een andere begroting maak je een
                    nieuwe.
                  </Quiet>
                </Stack>
              ) : null}
            </Section>
          ) : null}

          {current ? (
            <Stack gap="related">
              <QuoteCard
                quote={current}
                detail={detail.data}
                approval={approvals.isPending ? undefined : approval}
                mayManage={mayManage}
                isAdmin={isAdmin}
                busy={run.isPending}
                onAction={onCard}
              />
              {budgetMoved && canIssue && data?.content ? (
                <nldd-container layout="row" gap="16" vertical-alignment="center">
                  <Quiet>
                    De begroting staat nu op {formatEuro(data.content.total_cents)}.
                  </Quiet>
                  <Button text="Maak nieuwe offerte" size="sm" onClick={() => open('issue')} />
                </nldd-container>
              ) : null}
            </Stack>
          ) : null}

          {list.data && quotes.length === 0 && !showPreview ? (
            <EmptyNotice text="Er is nog geen offerte gemaakt" />
          ) : null}

          {earlier.length > 0 ? (
            <Section title="Eerdere offertes" level={2}>
              <nldd-list accessible-label="Eerdere offertes">
                {earlier.map((quote) => (
                  <EarlierQuoteRow key={quote.id} quote={quote} />
                ))}
              </nldd-list>
            </Section>
          ) : null}
        </Stack>
      </nldd-simple-section>

      <FormSheet
        open={dialog === 'issue'}
        title="Offerte maken"
        submitText="Maak offerte"
        busy={run.isPending}
        error={dialog === 'issue' ? formError : null}
        onClose={close}
        onSubmit={() =>
          submit(() =>
            issueQuote(assignmentId, {
              valid_until: validUntil || null,
              conditions: conditionsText.trim() || null,
              client_reference: clientReference.trim() || null,
            }),
          )
        }
      >
        <nldd-text>
          De offerte legt de begroting vast zoals die nu is
          {data?.content ? `: ${formatEuro(data.content.total_cents)}` : ''}. Ze krijgt een
          eigen kenmerk{waiting ? ' en vervangt de offerte die nu openstaat' : ''}. Daarna
          wijzigt ze niet meer.
        </nldd-text>
        <DateInput label="Geldig tot en met" value={validUntil} onChange={setValidUntil} optional />
        <TextInput
          label="Kenmerk van de opdrachtgever"
          hint="Bijvoorbeeld een zaak- of ordernummer. Staat op de offerte als 'Uw kenmerk'."
          value={clientReference}
          onChange={setClientReference}
          optional
        />
        <TextInput
          label="Voorwaarden"
          value={conditionsText}
          onChange={setConditions}
          optional
          multiline
        />
      </FormSheet>

      <OfferSheet
        open={dialog === 'offer'}
        channels={detail.data?.channels ?? []}
        busy={run.isPending}
        error={dialog === 'offer' ? formError : null}
        onClose={close}
        onOffer={(channel: OfferChannel, email: string) => {
          if (!current) return;
          submit(() =>
            offerQuote(current.id, channel === 'signing_link' ? { channel, email } : { channel }),
          );
        }}
      />

      <FormSheet
        open={dialog === 'approval'}
        title="Goedkeuring vragen"
        submitText="Vraag goedkeuring"
        busy={run.isPending}
        error={dialog === 'approval' ? formError : null}
        onClose={close}
        onSubmit={() => {
          if (!current) return;
          submit(() => requestApproval(current.id, approvalNote.trim() || null));
        }}
      >
        <nldd-text>
          Een collega met het recht om offertes goed te keuren beoordeelt offerte{' '}
          {current?.reference ?? ''}. Daarna kun je haar aanbieden. De opdrachtgever ziet hier
          niets van.
        </nldd-text>
        <TextInput
          label="Toelichting voor wie goedkeurt"
          value={approvalNote}
          onChange={setApprovalNote}
          optional
          multiline
        />
      </FormSheet>

      <FormSheet
        open={dialog === 'upload'}
        title="Getekende pdf vastleggen"
        submitText="Leg akkoord vast"
        busy={run.isPending}
        error={dialog === 'upload' ? formError : null}
        onClose={close}
        onSubmit={() => {
          if (!current) return;
          if (!file) {
            setFormError('Kies het getekende pdf-bestand.');
            return;
          }
          submit(() =>
            recordUploadedAcceptance(current.id, {
              file,
              signer_name: signerName.trim(),
              signer_email: signerEmail.trim(),
              signer_function: signerFunction.trim(),
              organisation_name: organisationName.trim(),
              signed_at: signedAt,
            }),
          );
        }}
      >
        <nldd-text>
          Hiermee leg je vast dat de opdrachtgever deze offerte heeft getekend. Dat is niet terug
          te draaien.
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
          hint="Alleen als de opdracht geen opdrachtgever noemt"
          value={organisationName}
          onChange={setOrganisationName}
          optional
        />
        <DateInput label="Datum van tekenen" value={signedAt} onChange={setSignedAt} optional />
      </FormSheet>

      <FormSheet
        open={dialog === 'reject'}
        title="Afwijzing vastleggen"
        submitText="Leg afwijzing vast"
        busy={run.isPending}
        error={dialog === 'reject' ? formError : null}
        onClose={close}
        onSubmit={() => {
          if (!current) return;
          submit(() => recordRejection(current.id, reason.trim() || null));
        }}
      >
        <nldd-text>
          Hiermee leg je vast dat de opdrachtgever deze offerte heeft afgewezen. Daarna kun je
          een nieuwe offerte maken.
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} optional multiline />
      </FormSheet>
    </>
  );
}
