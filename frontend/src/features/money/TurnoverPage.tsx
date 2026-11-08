import { TurnoverBlock } from '@/features/reports/SteeringView';
import { SteeringContent, YearWorksheet } from './YearWorksheet';

export function TurnoverPage() {
  return (
    <YearWorksheet title="Omzet">
      {(year) => (
        <SteeringContent
          year={year}
          block={(steering) =>
            steering.turnover && (
              <TurnoverBlock bare turnover={steering.turnover} year={steering.year} />
            )
          }
        />
      )}
    </YearWorksheet>
  );
}
