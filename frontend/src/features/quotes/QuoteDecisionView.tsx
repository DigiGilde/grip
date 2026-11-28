import { useState, type ReactNode } from 'react';
import { useMutation } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { Button, TextInput } from '@/features/assignments/ui';
import { formatEuro } from '@/lib/format';
import { FormSheet, Page, Quiet, Section, Stack, type PageBack } from '@/ui/layout';
import type { QuoteContent } from './api';
import { DecisionFailed, DecisionReceipt } from './DecisionReceipt';
import { QuoteContentTable } from './QuoteContentTable';
import { QuoteDetails } from './QuoteDetails';
import { beforeLeaving, leaveForDecision, type DecisionIntent } from './proof';
import { DocumentLink } from './ui';

export type Decision = 'accept' | 'reject';

/** What was filled in a sheet when it was sent. */
export interface DecisionValues {
  signerFunction: string;
  reason: string;
}

/** What was filled in before the browser left for the login. */
export interface DecisionDraft {
  decision?: Decision;
  signerFunction?: string;
  reason?: string;
}

interface QuoteDecisionViewProps {
  title: string;
  instanceName?: string;
  back?: PageBack;
  /** The receipt of a decision, or what became of the quote. Stands above the amount. */
  notice?: ReactNode;
  receipt?: { scope: 'signing' | 'proof'; evidenceId: string } | null;
  /** The decision did not go through. */
  failure?: { code: string; dismiss: () => void } | null;
  contractorName: string;
  /** Who signs, in a sentence: "Voorbeeldministerie", or "je organisatie". */
  signerLabel: string;
  /** Null where the reader may not see the content: `unreadable` stands in its place. */
  content: QuoteContent | null;
  unreadable?: ReactNode;
  /** Reference, validity: one quiet line under the amount. */
  byline: string;
  reference?: string | null;
  documentHref?: string;
  hash?: string | null;
  fileHash?: string | null;
  fileNote?: string | null;
  /** Whether a decision can still be made here, by this reader. */
  canDecide: boolean;
  draft?: DecisionDraft | null;
  /** Asks for the intent; the decision is made when the browser is back from the login. */
  createIntent: (decision: Decision, values: DecisionValues) => Promise<DecisionIntent>;
  /** Extra fields in the sheet for accepting, and the check that goes with them. */
  acceptFields?: ReactNode;
  checkAccept?: () => string | null;
  /** The sheet for accepting opens: the moment to start its extra fields. */
  onAcceptOpen?: () => void;
  /** Below the buttons. */
  children?: ReactNode;
}

/**
 * One quote and the decision on it: the page a director signs on and the two
 * sheets behind its buttons. The invited signer and the person with an
 * account get the same shape; each screen brings its own data and its own way
 * to ask for the intent.
 */
export function QuoteDecisionView({
  title,
  instanceName,
  back,
  notice,
  receipt,
  failure,
  contractorName,
  signerLabel,
  content,
  unreadable,
  byline,
  reference,
  documentHref,
  hash,
  fileHash,
  fileNote,
  canDecide,
  draft,
  createIntent,
  acceptFields,
  checkAccept,
  onAcceptOpen,
  children,
}: QuoteDecisionViewProps) {
  const [sheet, setSheet] = useState<Decision | null>(null);
  const [signerFunction, setSignerFunction] = useState(draft?.signerFunction ?? '');
  const [reason, setReason] = useState(draft?.reason ?? '');
  const [error, setError] = useState<string | null>(null);

  const leave = useMutation({
    mutationFn: (decision: Decision) => createIntent(decision, { signerFunction, reason }),
    onSuccess: leaveForDecision,
    onError: (failed) => setError(errorMessage(failed)),
  });
  const passkey = Boolean(leave.data?.passkey);

  const open = (next: Decision) => {
    setError(null);
    if (next === 'accept') onAcceptOpen?.();
    setSheet(next);
  };
  const send = (decision: Decision) => {
    if (decision === 'accept') {
      const problem = checkAccept?.() ?? null;
      if (problem) {
        setError(problem);
        return;
      }
    }
    setError(null);
    leave.mutate(decision);
  };
  const amount = content ? formatEuro(content.total_cents) : '';

  return (
    <>
      <Page kind="document" title={title} instanceName={instanceName} back={back}>
        {receipt ? (
          <Stack gap="related">
            <DecisionReceipt scope={receipt.scope} evidenceId={receipt.evidenceId} />
            <Quiet>{contractorName} ziet je besluit.</Quiet>
          </Stack>
        ) : (
          notice
        )}
        {failure ? (
          <DecisionFailed
            code={failure.code}
            onRetry={() => {
              failure.dismiss();
              open(draft?.decision ?? 'accept');
            }}
          />
        ) : null}

        {content ? (
          <>
            <Stack gap="close">
              <nldd-title
                size="display-3"
                heading-level={2}
                overline={`${contractorName} biedt aan`}
                text={amount}
              />
              {byline ? <Quiet>{byline}</Quiet> : null}
            </Stack>

            <QuoteContentTable content={content} label="Regels van de offerte" compact />

            {content.conditions ? (
              <Section title="Voorwaarden" level={2}>
                <nldd-text>
                  <p>{content.conditions}</p>
                </nldd-text>
              </Section>
            ) : null}

            <nldd-container layout="row" gap="16" vertical-alignment="center">
              {documentHref ? <DocumentLink href={documentHref} text="Bekijk pdf" newTab /> : null}
              {hash ? (
                <QuoteDetails
                  hash={hash}
                  documentHref={documentHref}
                  fileHash={fileHash ?? null}
                  fileNote={fileNote ?? null}
                  facts={[{ label: 'Kenmerk', value: reference ?? '' }]}
                />
              ) : null}
            </nldd-container>

            {canDecide ? (
              <Stack gap="related">
                <nldd-text>
                  <p>
                    Met je akkoord gaat {signerLabel} deze opdracht aan voor dit bedrag. Daarna kan{' '}
                    {contractorName} aan het werk. Vastgelegd wordt wie je bent, namens wie je
                    tekent en wanneer.
                  </p>
                </nldd-text>
                <nldd-button-group>
                  <Button text="Geef akkoord" appearance="primary" onClick={() => open('accept')} />
                  <Button text="Wijs af" onClick={() => open('reject')} />
                </nldd-button-group>
              </Stack>
            ) : null}
          </>
        ) : (
          unreadable
        )}
        {children}
      </Page>

      <FormSheet
        open={sheet === 'accept'}
        title="Akkoord geven"
        submitText="Log in en geef akkoord"
        busy={leave.isPending && sheet === 'accept'}
        error={sheet === 'accept' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => send('accept')}
      >
        <nldd-text>
          <p>
            Je geeft akkoord op {reference ? `offerte ${reference}` : 'deze offerte'} van {amount}.
            Een akkoord is niet terug te draaien.
          </p>
        </nldd-text>
        <nldd-text>
          <p>{beforeLeaving('accept', passkey)}</p>
        </nldd-text>
        <TextInput
          label="Je functie"
          value={signerFunction}
          onChange={setSignerFunction}
          optional
          hint="Staat bij je akkoord, bijvoorbeeld Directeur."
        />
        {acceptFields}
      </FormSheet>

      <FormSheet
        open={sheet === 'reject'}
        title="Offerte afwijzen"
        submitText="Log in en wijs af"
        busy={leave.isPending && sheet === 'reject'}
        error={sheet === 'reject' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => send('reject')}
      >
        <nldd-text>
          <p>
            {contractorName} ziet dat de offerte is afgewezen, met de reden die je hier geeft.
            Afwijzen is niet terug te draaien.
          </p>
        </nldd-text>
        <nldd-text>
          <p>{beforeLeaving('reject', passkey)}</p>
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} optional multiline />
      </FormSheet>
    </>
  );
}
