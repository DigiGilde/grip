import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import { assignmentTabPath } from '@/features/assignments/paths';
import { useCaseCourse } from '@/features/tasks/course';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { formatPeriod } from '@/lib/format';
import { PATHS } from '@/paths';
import { courseAction, type Course } from '@/ui/course';
import { LoadError, Loading, Quiet, SectionHeading, Stack, ThingHead } from '@/ui/layout';
import { PrimaryTakenContext } from '@/ui/primary';
import { CourseBar, CourseNow } from '@/ui/Workflow';
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
import { vacancyTabPath, type VacancyTabKey } from './paths';
import { PrepareRequestSheet } from './PrepareRequestSheet';
import { PublishSheet } from './ProcedureSection';
import { EditSheet, SubmitSheet } from './RoleSheets';
import {
  TAB_LABELS,
  VacancyShellContext,
  seesWholeVacancy,
  visibleTabs,
  type SharedSheet,
} from './shell';
import { PublishedLinks } from './TextWork';
import { Button, Paragraphs } from './ui';

function currentTab(id: string, pathname: string, tabs: VacancyTabKey[]): VacancyTabKey {
  const path = pathname.replace(/\/$/, '');
  return (
    tabs.find((tab) => tab !== 'request' && path.startsWith(vacancyTabPath(id, tab))) ?? 'request'
  );
}

/** The one thing the request needs that is not a field of its form. */
const MOTIVATION_MISSING = 'Vastgestelde aanleiding en motivatie';

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
      // Only the motivation is missing: that is written on the Tekst tab.
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
 * The one next step on the vacancy for this reader, as the server decides
 * it: done in a sheet here, or at the place it leads to. Null when it is
 * someone else's move, or when the reader already is where it is done.
 */
function nextStep(
  course: Course | null | undefined,
  pathname: string,
): { text: string; sheet: SharedSheet | null; href: string } | null {
  const action = courseAction(course);
  if (!action) return null;
  const sheet = sheetFor(course);
  const here = pathname.replace(/\/$/, '');
  const onlyMotivation =
    course?.next?.task_key === 'werving.aanvraag_voorbereiden' &&
    !sheet &&
    (course.next.missing ?? []).length > 0;
  const href = onlyMotivation ? `${action.href.replace(/\/$/, '')}/tekst` : action.href;
  const there = href.split('?')[0]?.replace(/\/$/, '');
  if (!sheet && there === here) return null;
  return { text: onlyMotivation ? 'Schrijf de motivatie' : action.text, sheet, href };
}

/** Function, where it belongs and what kind it is, in one quiet line. */
function Belonging({ vacancy, withStatus = true }: { vacancy: Vacancy; withStatus?: boolean }) {
  const facts = [
    vacancy.vacancy_type ? VACANCY_TYPE_LABELS[vacancy.vacancy_type] : null,
    scaleAndFte(vacancy.scale, vacancy.fte),
    formatPeriod(vacancy.start_date, vacancy.end_date),
    // Only in the answer for who may see staffing.
    vacancy.candidate_name ? `voor ${vacancy.candidate_name}` : '',
  ].filter(Boolean);
  return (
    <nldd-container layout="wrap" gap="8" vertical-alignment="center">
      {withStatus && (
        <nldd-badge color={STATUS_COLORS[vacancy.status]} text={STATUS_LABELS[vacancy.status]} />
      )}
      {vacancy.assignment_id && vacancy.assignment_name && (
        <RouterLinks>
          <nldd-link
            href={assignmentTabPath(vacancy.assignment_id, 'staffing')}
            text={vacancy.assignment_name}
          />
        </RouterLinks>
      )}
      <Quiet>{facts.join(' · ')}</Quiet>
    </nldd-container>
  );
}

/** What everyone sees of a published vacancy: the established text. */
function PublishedText({ vacancy }: { vacancy: Vacancy }) {
  if (!vacancy.published_text) return null;
  return (
    <nldd-simple-section>
      <Stack gap="related">
        <SectionHeading text="Vacaturetekst" />
        <Paragraphs text={vacancy.published_text.body} />
        <Quiet>{publishedOrigin(vacancy.published_text)}</Quiet>
      </Stack>
    </nldd-simple-section>
  );
}

const BACK = { href: PATHS.vacancies, text: 'Terug naar Vacatures' };

interface WholeHeadProps {
  vacancy: Vacancy;
  current: VacancyTabKey;
  instanceName?: string;
  course: Course | null | undefined;
  step: ReturnType<typeof nextStep>;
  onSheet: (sheet: SharedSheet) => void;
}

/** The head for who sees the whole vacancy: what is next, its course and its tabs. */
function WholeHead({ vacancy, current, instanceName, course, step, onSheet }: WholeHeadProps) {
  const navigate = useNavigate();
  const waits = Boolean(course?.next && !course.next.mine);
  return (
    <ThingHead
      title={vacancy.function_title}
      instanceName={instanceName}
      back={BACK}
      {...(step
        ? {
            action: (
              <Button
                text={step.text}
                appearance="primary"
                onClick={() => (step.sheet ? onSheet(step.sheet) : navigate(step.href))}
              />
            ),
          }
        : {})}
      tabs={{
        label: `Onderdelen van de vacature ${vacancy.function_title}`,
        current,
        items: visibleTabs(vacancy).map((tab) => ({
          key: tab,
          text: TAB_LABELS[tab],
          href: vacancyTabPath(vacancy.id, tab),
        })),
      }}
    >
      {course && <CourseNow course={course} tasksHref={vacancyTabPath(vacancy.id, 'tasks')} />}
      {course && !course.ended && (
        <CourseBar
          course={course}
          accessibleLabel={`Verloop van de vacature ${vacancy.function_title}`}
        />
      )}
      {/* The course says where it stands; the status only once it has ended. */}
      <Belonging vacancy={vacancy} withStatus={!course || Boolean(course.ended)} />
      <PublishedLinks vacancyId={vacancy.id} />
      {/* The sentence above already says whose move it is, when it is not the reader's. */}
      {!vacancy.permissions.can_edit && !waits && (
        <Quiet>
          Je kunt deze vacature bekijken. Wijzigen kan de aanvrager of wie de opdracht beheert.
        </Quiet>
      )}
    </ThingHead>
  );
}

/**
 * The frame around every page of one vacancy: a compact header with the
 * steps and the one primary action, and the tabs. Each tab is one concern.
 * The sheets that the step bar and a tab can both open live here.
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
  const current = vacancy ? currentTab(vacancy.id, pathname, visibleTabs(vacancy)) : 'request';
  const close = () => setSheet(null);
  // Where the vacancy stands and what is next, from the same facts as its tasks.
  const course = useCaseCourse('vacancy', vacancyId, whole).data?.course;
  const step = nextStep(course, pathname);

  return (
    <>
      {vacancy && whole ? (
        <WholeHead
          vacancy={vacancy}
          current={current}
          instanceName={instance?.name}
          course={course}
          step={step}
          onSheet={setSheet}
        />
      ) : (
        <ThingHead
          title={vacancy?.function_title ?? 'Vacature'}
          instanceName={instance?.name}
          back={BACK}
        >
          {query.isPending && <Loading />}
          {query.isError && (
            <LoadError
              error={query.error}
              retry={() => void query.refetch()}
              what="Deze vacature"
            />
          )}
          {vacancy && <Belonging vacancy={vacancy} />}
          {vacancy && <PublishedLinks vacancyId={vacancy.id} />}
        </ThingHead>
      )}
      {vacancy && !whole && <PublishedText vacancy={vacancy} />}
      {vacancy && whole && (
        <VacancyShellContext.Provider
          value={{
            vacancy,
            options: options.data,
            openSheet: setSheet,
            headerPrimary: step !== null,
          }}
        >
          <PrimaryTakenContext.Provider value={step !== null}>
            <Outlet />
          </PrimaryTakenContext.Provider>
        </VacancyShellContext.Provider>
      )}
      {vacancy && vacancy.permissions.can_edit && (
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
