import { PotentialBlock } from '@/features/reports/SteeringView';
import { SteeringContent, YearWorksheet } from './YearWorksheet';

export function PotentialPage() {
  return (
    <YearWorksheet title="Potentieel">
      {(year) => (
        <SteeringContent
          year={year}
          block={(steering) =>
            steering.pipeline && (
              <PotentialBlock bare pipeline={steering.pipeline} year={steering.year} />
            )
          }
        />
      )}
    </YearWorksheet>
  );
}
