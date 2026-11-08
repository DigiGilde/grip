import { YearAccountView } from '@/features/reports/YearAccountView';
import { YearWorksheet } from './YearWorksheet';

export function YearAccountPage() {
  return (
    <YearWorksheet title="Jaarverantwoording">
      {(year) => <YearAccountView bare year={year} />}
    </YearWorksheet>
  );
}
