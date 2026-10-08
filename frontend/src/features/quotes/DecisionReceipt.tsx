import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { Button } from '@/features/assignments/ui';
import { ErrorNotice, Facts, Loading, Stack } from '@/ui/layout';
import {
  DECISION_DONE,
  VERIFY_PATH,
  bundleUrl,
  canRetry,
  decisionErrorText,
  fetchEvidence,
  navigation,
  proofKeys,
  receiptFacts,
  statementPageUrl,
  type ProofScope,
} from './proof';
import { DocumentLink } from './ui';

interface ReceiptProps {
  scope: ProofScope;
  evidenceId: string;
  /** The quote's own file, as elsewhere. */
  pdfHref?: string;
}

/**
 * The receipt of a decision: what was decided and by whom, and the bundle to
 * keep. It says nothing about how the login went: the decision is recorded,
 * and nobody reading this can change what the identity provider did. Those
 * facts stand, neutrally, on the statement page and in the check of a bundle.
 */
export function DecisionReceipt({ scope, evidenceId, pdfHref }: ReceiptProps) {
  const query = useQuery({
    queryKey: proofKeys.evidence(scope, evidenceId),
    queryFn: () => fetchEvidence(scope, evidenceId),
    retry: false,
  });
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  const evidence = query.data;
  return (
    <Stack gap="related">
      <nldd-banner
        variant="success"
        text={DECISION_DONE[evidence.decision] ?? 'Het besluit is vastgelegd'}
        data-receipt={evidence.id}
      />
      <Facts label="Wat is vastgelegd" facts={receiptFacts(evidence)} labelWidth="140px" />
      <nldd-container layout="wrap" gap="16" vertical-alignment="center">
        <Button
          text="Download bewijs"
          appearance="primary"
          onClick={() => navigation.go(bundleUrl(scope, evidenceId))}
        />
        <DocumentLink
          href={statementPageUrl(scope, evidenceId)}
          text="Bekijk akkoordverklaring"
          newTab
        />
        {pdfHref ? <DocumentLink href={pdfHref} text="Bekijk pdf" newTab /> : null}
        <DocumentLink href={VERIFY_PATH} text="Controleer een bewijs" />
      </nldd-container>
    </Stack>
  );
}

/** The decision did not go through: what happened, that nothing was kept, and the way on. */
export function DecisionFailed({ code, onRetry }: { code: string; onRetry: () => void }) {
  return (
    <Stack gap="related">
      <nldd-banner
        variant="critical"
        text="Er is niets vastgelegd"
        supporting-text={decisionErrorText(code)}
        data-decision-error={code}
      />
      {canRetry(code) ? (
        <nldd-button-group>
          <Button text="Probeer opnieuw" appearance="primary" onClick={onRetry} />
        </nldd-button-group>
      ) : null}
    </Stack>
  );
}
