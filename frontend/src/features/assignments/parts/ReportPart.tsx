import { useParams } from 'react-router-dom';
import { AssignmentReportContent } from '@/features/reports/AssignmentReportPage';
import { AssignmentPartPage } from '../AssignmentPartPage';

export function ReportPart() {
  const { assignmentId = '' } = useParams();
  return (
    <AssignmentPartPage part="report" kind="worksheet">
      <AssignmentReportContent assignmentId={assignmentId} />
    </AssignmentPartPage>
  );
}
