import { CaseHistory } from '@/features/history/History';
import { useVacancyShell } from '../shell';
import { VacancyPartPage } from '../VacancyPartPage';

export function HistoryPart() {
  const { vacancy } = useVacancyShell();
  return (
    <VacancyPartPage part="history" kind="list">
      <CaseHistory kind="vacancy" caseId={vacancy.id} />
    </VacancyPartPage>
  );
}
