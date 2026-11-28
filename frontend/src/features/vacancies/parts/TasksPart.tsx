import { CaseTasks } from '@/features/tasks/CaseTasks';
import { useVacancyShell } from '../shell';
import { VacancyPartPage } from '../VacancyPartPage';

export function TasksPart() {
  const { vacancy } = useVacancyShell();
  return (
    <CaseTasks
      kind="vacancy"
      caseId={vacancy.id}
      frame={(action, content) => (
        <VacancyPartPage part="tasks" kind="list" action={action}>
          {content}
        </VacancyPartPage>
      )}
    />
  );
}
