import { Section } from '@/ui/layout';
import { ProcedureSection } from '../ProcedureSection';
import { useVacancyShell } from '../shell';
import { TextWork } from '../TextWork';
import { VacancyPartPage } from '../VacancyPartPage';

export function TextPart() {
  const { vacancy } = useVacancyShell();
  return (
    <VacancyPartPage part="text" kind="document" spacing="sections">
      <TextWork vacancy={vacancy} />
      {vacancy.procedure.length > 0 && (
        <Section title="Procedure">
          <ProcedureSection vacancy={vacancy} />
        </Section>
      )}
    </VacancyPartPage>
  );
}
