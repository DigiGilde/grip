import { useQuery } from '@tanstack/react-query';
import { assignmentPath } from '@/features/assignments/paths';
import { TakeOverButton } from '@/features/tasks/TakeOver';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate, formatPeriod } from '@/lib/format';
import { PATHS } from '@/paths';
import { lowerFirst } from '@/ui/course';
import { Page, Stack } from '@/ui/layout';
import { LinkRows, type LinkRow } from '@/ui/LinkRows';
import { CourseNow } from '@/ui/Workflow';
import { fetchVacancyHire, hireKey, type Vacancy } from './api';
import { STATUS_COLORS, STATUS_LABELS, VACANCY_TYPE_LABELS, scaleAndFte } from './labels';
import { vacancyPartPath } from './paths';
import type { VacancyPart } from './partsApi';
import { useVacancyShell } from './shell';
import { PublishedLinks } from './TextWork';
import { StepButton } from './VacancyPartPage';

const STEPS: readonly VacancyPart['key'][] = ['request', 'decisions', 'text', 'fulfilment'];

const TAGS: Partial<Record<NonNullable<VacancyPart['state']>, LinkRow['tag']>> = {
  done: { text: 'Klaar', color: 'success' },
  current: { text: 'Nu aan de beurt', color: 'accent' },
};

/** What kind of vacancy it is and for when. */
function kindAndPeriod(vacancy: Vacancy): string {
  return [
    vacancy.vacancy_type ? VACANCY_TYPE_LABELS[vacancy.vacancy_type] : '',
    formatPeriod(vacancy.start_date, vacancy.end_date),
  ]
    .filter(Boolean)
    .join(', ');
}

/**
 * Where the vacancy belongs and what it is. Kind and period stand here only
 * for a reader without the row Gegevens, who has no other place to read them.
 */
function leadOf(vacancy: Vacancy, hasDetails: boolean): string {
  return [
    vacancy.assignment_name ? `Vacature bij ${vacancy.assignment_name}` : 'Vacature',
    lowerFirst(scaleAndFte(vacancy.scale, vacancy.fte)),
    hasDetails ? '' : lowerFirst(kindAndPeriod(vacancy)),
  ]
    .filter(Boolean)
    .join(', ');
}

function rowOf(vacancy: Vacancy, part: VacancyPart): LinkRow {
  const told =
    part.state === 'current' && part.notice ? `Jij: ${lowerFirst(part.notice)}` : part.notice;
  const notice = told || (part.key === 'details' ? kindAndPeriod(vacancy) : '');
  const tag = part.state ? TAGS[part.state] : undefined;
  return {
    key: part.key,
    text: part.label,
    href: vacancyPartPath(vacancy.id, part.key),
    ...(notice ? { notice } : {}),
    ...(tag ? { tag } : {}),
  };
}

/**
 * How a filled vacancy ended: who starts, and when. The name is there only
 * for who may read staffing; without it the date alone.
 */
function Filled({ vacancy }: { vacancy: Vacancy }) {
  const filled = vacancy.status === 'filled';
  const hire = useQuery({
    queryKey: hireKey(vacancy.id),
    queryFn: () => fetchVacancyHire(vacancy.id),
    enabled: filled,
  });
  const found = hire.data?.hire;
  if (!filled || !found) return null;
  const started = found.stage !== 'prospective';
  const when = `${started ? 'is gestart' : 'start'} op ${formatDate(found.start_date)}`;
  return (
    <nldd-text size="md">
      <p>
        {found.person_name
          ? `Vervuld: ${found.person_name} ${when}.`
          : `Vervuld: de collega ${when}.`}
      </p>
    </nldd-text>
  );
}

/** Where a vacancy opens: what is next, and its steps as rows with their stand. */
export function VacancyLanding() {
  const { vacancy, parts, tasksLink, course, step, instanceName } = useVacancyShell();
  const rows = (keep: (part: VacancyPart) => boolean) =>
    parts.filter(keep).map((part) => rowOf(vacancy, part));
  const others = rows((part) => !STEPS.includes(part.key));
  // Once it has ended no step says where it stands; a filled one says so itself.
  const ended = Boolean(course?.ended) && vacancy.status !== 'filled';
  const tasksHref = tasksLink ? vacancyPartPath(vacancy.id, 'tasks') : null;
  // "En nog N taken voor jou" is the link to the tasks when there is such a line.
  const moreLinked =
    tasksHref !== null && course && !course.ended && course.next && (course.more_to_do ?? 0) > 0;
  const hasDetails = parts.some((part) => part.key === 'details');
  // Gegevens links the assignment; without that row the way there is here. The
  // server gives the id only to who may open the assignment.
  const assignmentHref =
    !hasDetails && vacancy.assignment_id ? assignmentPath(vacancy.assignment_id) : null;
  return (
    <Page
      kind="list"
      title={vacancy.function_title}
      lead={leadOf(vacancy, hasDetails)}
      instanceName={instanceName}
      back={{ href: PATHS.vacancies, text: 'Terug naar Vacatures' }}
      action={step ? <StepButton step={step} /> : undefined}
    >
      {ended && (
        <nldd-container layout="wrap">
          <nldd-badge color={STATUS_COLORS[vacancy.status]} text={STATUS_LABELS[vacancy.status]} />
        </nldd-container>
      )}
      {course && (
        <RouterLinks>
          <CourseNow course={course} {...(tasksHref ? { tasksHref } : {})} />
        </RouterLinks>
      )}
      <Filled vacancy={vacancy} />
      <TakeOverButton course={course} />
      <PublishedLinks vacancyId={vacancy.id} />
      <Stack gap="related">
        {assignmentHref && vacancy.assignment_name && (
          <RouterLinks>
            <div>
              <nldd-link href={assignmentHref} size="sm" text={`Naar ${vacancy.assignment_name}`} />
            </div>
          </RouterLinks>
        )}
        {tasksHref && !moreLinked && (
          <RouterLinks>
            <div>
              <nldd-link href={tasksHref} size="sm" text="Alle taken van deze vacature" />
            </div>
          </RouterLinks>
        )}
        <LinkRows
          label={`Stappen van de vacature ${vacancy.function_title}`}
          rows={rows((part) => STEPS.includes(part.key))}
        />
      </Stack>
      {others.length > 0 && (
        <LinkRows label={`Over de vacature ${vacancy.function_title}`} rows={others} />
      )}
    </Page>
  );
}
