import { assignmentPartPath } from '@/features/assignments/paths';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatPeriod } from '@/lib/format';
import { Facts, Quiet, type Fact } from '@/ui/layout';
import { CONTRACT_TYPE_LABELS, VACANCY_TYPE_LABELS, scaleAndFte } from '../labels';
import { useVacancyShell } from '../shell';
import { Button } from '../ui';
import { VacancyPartPage } from '../VacancyPartPage';

/** What the vacancy is, as far as the reader may read it, and the way to change it. */
export function DetailsPart() {
  const { vacancy, openSheet } = useVacancyShell();
  const editable = vacancy.permissions.can_edit && ['draft', 'requested'].includes(vacancy.status);
  const facts: Fact[] = [
    {
      label: 'Soort',
      value: vacancy.vacancy_type ? VACANCY_TYPE_LABELS[vacancy.vacancy_type] : '',
    },
    { label: 'Schaal en FTE', value: scaleAndFte(vacancy.scale, vacancy.fte) },
    { label: 'Periode', value: formatPeriod(vacancy.start_date, vacancy.end_date) },
    {
      label: 'Opdracht',
      value: vacancy.assignment_id ? (
        <nldd-link
          href={assignmentPartPath(vacancy.assignment_id, 'landing')}
          text={vacancy.assignment_name ?? 'Opdracht'}
        />
      ) : (
        (vacancy.assignment_name ?? '')
      ),
    },
    { label: 'Kandidaat', value: vacancy.candidate_name ?? '' },
    {
      label: 'Type contract',
      value: vacancy.contract_type ? CONTRACT_TYPE_LABELS[vacancy.contract_type] : '',
    },
    { label: 'Aanvrager', value: vacancy.requester_name ?? '' },
  ];
  return (
    <VacancyPartPage part="details" kind="document">
      {!vacancy.permissions.can_edit && (
        <Quiet>
          Je kunt deze vacature bekijken. Wijzigen kan de aanvrager of wie de opdracht beheert.
        </Quiet>
      )}
      <RouterLinks>
        <Facts label="Gegevens van de vacature" facts={facts} omitEmpty />
      </RouterLinks>
      {editable && (
        <nldd-button-group>
          <Button text="Wijzig functie, fte of periode" onClick={() => openSheet('edit')} />
        </nldd-button-group>
      )}
    </VacancyPartPage>
  );
}
