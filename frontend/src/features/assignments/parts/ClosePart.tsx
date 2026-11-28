import { MonthClosePage } from '@/features/month-close/MonthClosePage';
import { AssignmentPartPage } from '../AssignmentPartPage';

export function ClosePart() {
  return (
    <AssignmentPartPage part="close" kind="worksheet">
      <MonthClosePage />
    </AssignmentPartPage>
  );
}
