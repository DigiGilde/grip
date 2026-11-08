import { useParams } from 'react-router-dom';
import { CaseTasks } from '@/features/tasks/CaseTasks';
import { AssignmentPartPage } from '../AssignmentPartPage';

export function TasksPart() {
  const { assignmentId = '' } = useParams();
  return (
    <CaseTasks
      kind="assignment"
      caseId={assignmentId}
      frame={(action, content) => (
        <AssignmentPartPage part="tasks" kind="list" action={action}>
          {content}
        </AssignmentPartPage>
      )}
    />
  );
}
