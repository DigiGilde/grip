import { QuotePage } from '@/features/quotes/QuotePage';
import { AssignmentPartPage } from '../AssignmentPartPage';

export function QuotePart() {
  return (
    <AssignmentPartPage part="quote" kind="document">
      <QuotePage />
    </AssignmentPartPage>
  );
}
