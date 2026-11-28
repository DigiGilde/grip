import { InvestmentView } from '@/features/reports/InvestmentView';
import { YearWorksheet } from './YearWorksheet';

export function InvestmentPage() {
  return (
    <YearWorksheet title="Investeerruimte">
      {(year) => <InvestmentView bare year={year} />}
    </YearWorksheet>
  );
}
