import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { momentOf, useMoments, useStand } from '@/features/chronicle/api';
import { ChronicleView } from '@/features/chronicle/ChronicleView';
import { RemoveTextSheet } from '@/features/chronicle/RemoveTextSheet';
import { CaseHistory } from '@/features/history/History';
import { ActionBar, type ActionBarAction } from '@/ui/ActionBar';
import { LoadError, Loading } from '@/ui/layout';
import { AssignmentPartPage } from '../AssignmentPartPage';
import { assignmentPartPath } from '../paths';

const SHOW_PARAM = 'toon';
const SHOW_CHANGES = 'wijzigingen';

/** The bar over one moment: the beheerder may take a typed text out of it. */
function MomentBar({
  assignmentId,
  seq,
  way,
}: {
  assignmentId: string;
  seq: number;
  way: ActionBarAction;
}) {
  const stand = useStand(assignmentId, seq);
  const [removing, setRemoving] = useState(false);
  const texts = stand.isPlaceholderData ? [] : (stand.data?.removable_texts ?? []);
  return (
    <>
      <ActionBar
        label="Geschiedenis"
        actions={[way]}
        {...(texts.length > 0
          ? {
              more: {
                name: 'dit moment',
                actions: [{ text: 'Verwijder een tekst', onSelect: () => setRemoving(true) }],
              },
            }
          : {})}
      />
      <RemoveTextSheet
        assignmentId={assignmentId}
        seq={seq}
        texts={texts}
        open={removing}
        onClose={() => setRemoving(false)}
      />
    </>
  );
}

/**
 * What happened with an assignment: its moments, a moment as it stood, or
 * every change. Each has its own address; a case from before the moments
 * has only the changes.
 */
export function AssignmentHistory({ assignmentId }: { assignmentId: string }) {
  const [params] = useSearchParams();
  const chronicle = useMoments(assignmentId);
  const seq = momentOf(params);
  const changes = seq === null && params.get(SHOW_PARAM) === SHOW_CHANGES;

  if (chronicle.isPending) return <Loading />;
  if (chronicle.isError) {
    return <LoadError error={chronicle.error} retry={() => void chronicle.refetch()} />;
  }
  const moments = chronicle.data.items;
  if (moments.length === 0 && seq === null) {
    return <CaseHistory kind="assignment" caseId={assignmentId} />;
  }
  const here = assignmentPartPath(assignmentId, 'history');
  const way: ActionBarAction = changes
    ? { text: 'Bekijk de momenten', href: here }
    : { text: 'Bekijk de wijzigingen', href: `${here}?${SHOW_PARAM}=${SHOW_CHANGES}` };
  return (
    <>
      {seq === null ? (
        <ActionBar label="Geschiedenis" actions={[way]} />
      ) : (
        <MomentBar assignmentId={assignmentId} seq={seq} way={way} />
      )}
      {changes ? (
        <CaseHistory kind="assignment" caseId={assignmentId} />
      ) : (
        <ChronicleView assignmentId={assignmentId} moments={moments} seq={seq} />
      )}
    </>
  );
}

export function HistoryPart() {
  const { assignmentId = '' } = useParams();
  return (
    <AssignmentPartPage part="history" kind="list">
      <AssignmentHistory assignmentId={assignmentId} />
    </AssignmentPartPage>
  );
}
