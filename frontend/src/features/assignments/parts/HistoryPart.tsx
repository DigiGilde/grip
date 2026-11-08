import { useParams } from 'react-router-dom';
import { CaseHistory } from '@/features/history/History';
import { AssignmentPartPage } from '../AssignmentPartPage';

export function HistoryPart() {
  const { assignmentId = '' } = useParams();
  return (
    <AssignmentPartPage part="history" kind="list">
      <CaseHistory kind="assignment" caseId={assignmentId} />
    </AssignmentPartPage>
  );
}
