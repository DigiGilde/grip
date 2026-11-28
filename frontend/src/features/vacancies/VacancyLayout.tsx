import { PageBoundary } from '@/PageBoundary';
import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Outlet, useLocation, useParams } from 'react-router-dom';
import { assignmentPartPath } from '@/features/assignments/paths';
import { useCaseCourse } from '@/features/tasks/course';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { formatPeriod } from '@/lib/format';
import { PATHS } from '@/paths';
import { courseAction, type Course } from '@/ui/course';
import { LoadError, Loading, NoAccess, Page, Quiet, SectionHeading, Stack } from '@/ui/layout';
import { VACANCY_KEYS, fetchVacancy, type Vacancy } from './api';
import { HireSheet } from './HireSheets';
import { useVacancyOptions } from './hooks';
import {
  STATUS_COLORS,
  STATUS_LABELS,
  VACANCY_TYPE_LABELS,
  publishedOrigin,
  scaleAndFte,
} from './labels';
import { vacancyPartAt, vacancyPartPath } from './paths';
import { fetchVacancyParts, vacancyPartsKey, type VacancyPart } from './partsApi';
import { PrepareRequestSheet } from './PrepareRequestSheet';
import { PublishSheet } from './ProcedureSection';
import { EditSheet, SubmitSheet } from './RoleSheets';
import { VacancyShellContext, seesWholeVacancy, type SharedSheet, type VacancyStep } from './shell';
import { PublishedLinks } from './TextWork';
import { NOT_FOR_THIS_READER } from './VacancyPartPage';
import { Paragraphs } from './ui';

/** The one thing the request needs that is not a field of its form. */
const MOTIVATION_MISSING = 'een vastgestelde aanleiding en motivatie';

/**
 * The steps that are done in a sheet of this shell, by the kind of work the
 * server names. Any other step is done at the place its link leads to.
 */
function sheetFor(course: Course | null | undefined): SharedSheet | null {
  const next = course?.next;
  if (!next?.mine) return null;
  switch (next.task_key) {
    case 'werving.aanvraag_voorbereiden': {
      const missing = next.missing ?? [];
      if (missing.length === 0) return 'submit';
      // Only the motivation is missing: that is written under Tekst.
      return missing.every((item) => item === MOTIVATION_MISSING) ? null : 'prepare';
    }
    case 'werving.openstellen':
      return 'publish';
    case 'werving.vervullen':
      return 'hire';
    default:
      return null;
  }
}

/**
 * The primary button of the page the reader is on, as the server decides the
 * next step. The landing always has it. A part has it only when the step is
 * done in a sheet of that part; a step done in the part itself is the part's
 * own button, and on the request its rows open the sheet that fills it. A
 * step that leads to a part the reader does not have is not offered.
 */
function nextStep(
  vacancyId: string,
  course: Course | null | undefined,
  pathname: string,
  parts: readonly VacancyPart[],
): VacancyStep | null {
  const action = courseAction(course);
  if (!action) return null;
  const sheet = sheetFor(course);
  const onlyMotivation =
    course?.next?.task_key === 'werving.aanvraag_voorbereiden' &&
    !sheet &&
    (course.next.missing ?? []).length > 0;
  // Not only to the part: the address asks it to open the writing at once.
  const href = onlyMotivation
    ? `${vacancyPartPath(vacancyId, 'text')}?schrijf=motivation`
    : action.href;
  const target = vacancyPartAt(vacancyId, href);
  if (target && !['landing', 'tasks'].includes(target)) {
    if (!parts.some((part) => part.key === target)) return null;
  }
  const here = vacancyPartAt(vacancyId, pathname);
  if (here !== 'landing' && (!sheet || sheet === 'prepare' || target !== here)) return null;
  return { text: onlyMotivation ? 'Schrijf de motivatie' : action.text, sheet, href };
}

/** Function, where it belongs and what kind it is, in one quiet line. */
function Belonging({ vacancy }: { vacancy: Vacancy }) {
  const facts = [
    vacancy.vacancy_type ? VACANCY_TYPE_LABELS[vacancy.vacancy_type] : null,
    scaleAndFte(vacancy.scale, vacancy.fte),
    formatPeriod(vacancy.start_date, vacancy.end_date),
    // Only in the answer for who may see staffing.
    vacancy.candidate_name ? `voor ${vacancy.candidate_name}` : '',
  ].filter(Boolean);
  return (
    <nldd-container layout="wrap" gap="8" vertical-alignment="center">
      <nldd-badge color={STATUS_COLORS[vacancy.status]} text={STATUS_LABELS[vacancy.status]} />
      {vacancy.assignment_id && vacancy.assignment_name && (
        <RouterLinks>
          <nldd-link
            href={assignmentPartPath(vacancy.assignment_id, 'landing')}
            text={vacancy.assignment_name}
          />
        </RouterLinks>
      )}
      <Quiet>{facts.join(' · ')}</Quiet>
    </nldd-container>
  );
}

const BACK = { href: PATHS.vacancies, text: 'Terug naar Vacatures' };

/** What everyone sees of a published vacancy: the established text, and no parts. */
function PublishedVacancy({
  vacancy,
  instanceName,
  onPart,
}: {
  vacancy: Vacancy;
  instanceName: string | undefined;
  onPart: boolean;
}) {
  if (onPart) {
    return (
      <Page
        kind="document"
        title={vacancy.function_title}
        instanceName={instanceName}
        back={{
          href: vacancyPartPath(vacancy.id, 'landing'),
          text: `Terug naar ${vacancy.function_title}`,
        }}
      >
        <NoAccess who={NOT_FOR_THIS_READER} />
      </Page>
    );
  }
  return (
    <Page kind="document" title={vacancy.function_title} instanceName={instanceName} back={BACK}>
      <Belonging vacancy={vacancy} />
      <PublishedLinks vacancyId={vacancy.id} />
      {vacancy.published_text && (
        <Stack gap="related">
          <SectionHeading text="Vacaturetekst" />
          <Paragraphs text={vacancy.published_text.body} />
          <Quiet>{publishedOrigin(vacancy.published_text)}</Quiet>
        </Stack>
      )}
    </Page>
  );
}

/**
 * Loads one vacancy for all its pages and holds what they share: the parts,
 * the course, and the sheets that the head and a part can both open. Each
 * page draws its own head.
 */
export function VacancyLayout() {
  const { vacancyId = '' } = useParams();
  const { pathname } = useLocation();
  const instance = useInstance();
  const options = useVacancyOptions();
  const [sheet, setSheet] = useState<SharedSheet | null>(null);
  const query = useQuery({
    queryKey: VACANCY_KEYS.detail(vacancyId),
    queryFn: () => fetchVacancy(vacancyId),
    enabled: vacancyId !== '',
    retry: false,
  });
  const vacancy = query.data;
  const whole = vacancy ? seesWholeVacancy(vacancy) : false;
  const close = () => setSheet(null);
  // Where the vacancy stands and what is next, from the same facts as its tasks.
  const course = useCaseCourse('vacancy', vacancyId, whole).data?.course;
  const partsQuery = useQuery({
    queryKey: vacancyPartsKey(vacancyId),
    queryFn: () => fetchVacancyParts(vacancyId),
    enabled: whole && vacancyId !== '',
    retry: false,
    staleTime: 0,
    placeholderData: keepPreviousData,
  });
  const parts = partsQuery.data?.parts ?? [];
  const step = nextStep(vacancyId, course, pathname, parts);

  if (!vacancy) {
    return (
      <Page kind="document" title="Vacature" instanceName={instance?.name} back={BACK}>
        {query.isPending && <Loading />}
        {query.isError && (
          <LoadError error={query.error} retry={() => void query.refetch()} what="Deze vacature" />
        )}
      </Page>
    );
  }
  if (!whole) {
    return (
      <PublishedVacancy
        vacancy={vacancy}
        instanceName={instance?.name}
        onPart={vacancyPartAt(vacancy.id, pathname) !== 'landing'}
      />
    );
  }
  return (
    <>
      {partsQuery.data ? (
        <VacancyShellContext.Provider
          value={{
            vacancy,
            options: options.data,
            instanceName: instance?.name,
            openSheet: setSheet,
            parts,
            tasksLink: partsQuery.data.tasks_link,
            course,
            step,
            headerPrimary: step !== null,
            nextTask: course?.next?.mine ? (course.next.task_key ?? null) : null,
          }}
        >
          <PageBoundary resetKey={pathname}>
            <Outlet />
          </PageBoundary>
        </VacancyShellContext.Provider>
      ) : (
        <Page
          kind="document"
          title={vacancy.function_title}
          instanceName={instance?.name}
          back={BACK}
        >
          {partsQuery.isError ? (
            <LoadError error={partsQuery.error} retry={() => void partsQuery.refetch()} />
          ) : (
            <Loading />
          )}
        </Page>
      )}
      {vacancy.permissions.can_edit && (
        <>
          <EditSheet
            // A fresh form per saved state, so the fields show what was saved.
            key={`edit-${vacancy.status}-${vacancy.function_title}-${vacancy.fte}-${vacancy.start_date}-${vacancy.end_date}`}
            vacancy={vacancy}
            options={options.data}
            open={sheet === 'edit'}
            onClose={close}
          />
          <SubmitSheet vacancy={vacancy} open={sheet === 'submit'} onClose={close} />
          <PrepareRequestSheet
            key={`prepare-${vacancy.function_group_id}-${vacancy.fgr_function_name}-${vacancy.scale}-${vacancy.contract_type}-${vacancy.addressee_name}`}
            vacancy={vacancy}
            options={options.data}
            open={sheet === 'prepare'}
            onClose={close}
          />
          <PublishSheet
            key={`publish-${vacancy.status}-${(vacancy.channels ?? []).join(',')}`}
            vacancy={vacancy}
            options={options.data}
            open={sheet === 'publish'}
            onClose={close}
          />
          <HireSheet vacancy={vacancy} open={sheet === 'hire'} onClose={close} />
        </>
      )}
    </>
  );
}
