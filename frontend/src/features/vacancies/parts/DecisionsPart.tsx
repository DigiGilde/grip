import { DecisionsSection } from '../DecisionsSection';
import { useVacancyShell } from '../shell';
import { VacancyPartPage } from '../VacancyPartPage';

export function DecisionsPart() {
  const { vacancy } = useVacancyShell();
  return (
    <VacancyPartPage part="decisions" kind="document">
      <DecisionsSection vacancy={vacancy} />
    </VacancyPartPage>
  );
}
