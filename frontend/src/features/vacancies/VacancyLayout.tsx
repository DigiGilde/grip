import { StepBar } from '@/ui/StepBar';
import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { orUndef } from '@/components/nldd/events';
import { assignmentTabPath } from '@/features/assignments/paths';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatPeriod } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import { ErrorNotice, Loading, Quiet, SectionHeading, Stack } from '@/ui/layout';
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
  STEP_TABS,
  TAB_LABELS,
  VacancyShellContext,
  seesWholeVacancy,
  visibleTabs,
  type SharedSheet,
} from './shell';
import { vacancySteps, type StepAction } from './steps';
import { PublishedLinks } from './TextWork';
import { Button, Paragraphs } from './ui';

function currentTab(id: string, pathname: string, tabs: VacancyTabKey[]): VacancyTabKey {
  const path = pathname.replace(/\/$/, '');
  return (
    tabs.find((tab) => tab !== 'request' && path.startsWith(vacancyTabPath(id, tab))) ?? 'request'
  );
}

function Tabs({ vacancy, current }: { vacancy: Vacancy; current: VacancyTabKey }) {
  const ref = useRef<HTMLElement>(null);
  useRouterLinks(ref);
  // Each tab is a page with its own address, so this is navigation: the
  // design system then renders a nav landmark and marks the current page.
  return (
    <nldd-tab-bar
      ref={ref}
      navigation
      accessible-label={`Onderdelen van de vacature ${vacancy.function_title}`}
    >
      {visibleTabs(vacancy).map((tab) => (
        <nldd-tab-bar-item
          key={tab}
          href={vacancyTabPath(vacancy.id, tab)}
          text={TAB_LABELS[tab]}
          current={orUndef(tab === current)}
        />
      ))}
    </nldd-tab-bar>
  );
}

/** What the one primary action of each step is called. */
const ACTION_TEXT: Record<StepAction, string> = {
  prepare: 'Bereid aanvraag voor',
  submit: 'Vraag aan',
  decide: 'Naar advies en akkoord',
  open: 'Stel open',
  fill: 'Vervul',
};

const ACTION_SHEET: Partial<Record<StepAction, SharedSheet>> = {
  prepare: 'prepare',
  submit: 'submit',
  open: 'publish',
  fill: 'hire',
};

interface StepsProps {
  vacancy: Vacancy;
  current: VacancyTabKey;
  onSheet: (sheet: SharedSheet) => void;
}

/** Where the vacancy stands, with the one primary action of the current step. */
function Steps({ vacancy, current, onSheet }: StepsProps) {
  const navigate = useNavigate();
  const steps = vacancySteps(vacancy);
  if (!steps) return null;
  const action = steps.action;
  const sheet = action ? ACTION_SHEET[action] : undefined;
  // A step without a sheet of its own is done on its tab. There the tab
  // carries the action, so the header has none.
  const elsewhere = action && !sheet && STEP_TABS[action] !== current;
  return (
    <Stack gap="related">
      <StepBar
        steps={steps.items.map((text) => ({ text }))}
        current={steps.current}
        accessibleLabel="Stappen van de vacature"
      />
      {action && (sheet || elsewhere) && (
        <nldd-button-group>
          <Button
            text={ACTION_TEXT[action]}
            appearance="primary"
            onClick={() =>
              sheet ? onSheet(sheet) : navigate(vacancyTabPath(vacancy.id, STEP_TABS[action]))
            }
          />
        </nldd-button-group>
      )}
    </Stack>
  );
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
    <nldd-container layout="row" gap="8" vertical-alignment="center">
      <nldd-badge color={STATUS_COLORS[vacancy.status]} text={STATUS_LABELS[vacancy.status]} />
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
  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const whole = vacancy ? seesWholeVacancy(vacancy) : false;
  const current = vacancy ? currentTab(vacancy.id, pathname, visibleTabs(vacancy)) : 'request';
  const close = () => setSheet(null);

  return (
    <>
      <nldd-simple-section>
        <PageHeading text={vacancy?.function_title ?? 'Vacature'} instanceName={instance?.name} />
        <Stack gap="related">
          {query.isPending && <Loading />}
          {query.isError && (
            <ErrorNotice
              message={
                notFound
                  ? 'Deze vacature bestaat niet, of je kunt haar niet inzien.'
                  : errorMessage(query.error)
              }
            />
          )}
          {query.isError && (
            <RouterLinks>
              <nldd-link href={PATHS.vacancies} text="Naar alle vacatures" size="md" />
            </RouterLinks>
          )}
          {vacancy && <Belonging vacancy={vacancy} />}
          {vacancy && <PublishedLinks vacancyId={vacancy.id} />}
          {vacancy && whole && (
            <>
              <Steps vacancy={vacancy} current={current} onSheet={setSheet} />
              <Tabs vacancy={vacancy} current={current} />
            </>
          )}
        </Stack>
      </nldd-simple-section>
      {vacancy && !whole && <PublishedText vacancy={vacancy} />}
      {vacancy && whole && (
        <VacancyShellContext.Provider
          value={{ vacancy, options: options.data, openSheet: setSheet }}
        >
          <Outlet />
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
