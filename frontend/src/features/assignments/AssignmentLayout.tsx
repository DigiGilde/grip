import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { useCaseCourse } from '@/features/tasks/course';
import { TakeOverButton } from '@/features/tasks/TakeOver';
import { useInstance } from '@/layout/useInstance';
import { formatEuro, formatPeriod } from '@/lib/format';
import { Button } from '@/ui/Button';
import { KeyFigures, ThingHead, type KeyFigure } from '@/ui/layout';
import { PrimaryTakenContext } from '@/ui/primary';
import { courseAction } from '@/ui/course';
import { CourseBar, CourseNow } from '@/ui/Workflow';
import { PATHS } from '@/paths';
import {
  assignmentKeys,
  fetchAssignment,
  transitionAssignment,
  type AssignmentDetail,
} from './api';
import { fetchAssignmentFinance, financeKeys } from './financeApi';
import {
  FIGURE_LABELS,
  NOTHING_PLANNED_TEXT,
  nothingPlanned,
  varianceText,
  varianceWord,
} from './financeText';
import { relationText, STATUS_COLORS, statusLabel } from './labels';
import { assignmentTabPath, type AssignmentTabKey } from './paths';
import { AssignmentShellContext, TAB_LABELS, visibleTabs } from './shell';
import { LoadError } from '@/ui/layout';
import { ErrorNotice, Loading } from './ui';

/** The whole period: the header never follows a year filter on a tab. */
const WHOLE_PERIOD = 'all';

/** The tab the address is on; none for an address that is no tab the reader has. */
function currentTab(
  id: string,
  pathname: string,
  tabs: AssignmentTabKey[],
): AssignmentTabKey | undefined {
  const path = pathname.replace(/\/$/, '');
  const deeper = tabs.find(
    (tab) => tab !== 'overview' && path.startsWith(assignmentTabPath(id, tab)),
  );
  if (deeper) return deeper;
  return path === assignmentTabPath(id, 'overview').replace(/\/$/, '') ? 'overview' : undefined;
}

/** Begroot, gerealiseerd, verwacht totaal and the variance, for who may see money. */
function Figures({ assignment }: { assignment: AssignmentDetail }) {
  const query = useQuery({
    queryKey: financeKeys.assignment(assignment.id, WHOLE_PERIOD),
    queryFn: () => fetchAssignmentFinance(assignment.id, WHOLE_PERIOD),
  });
  const totals = query.data?.totals;
  if (!totals) return null;
  // Nothing budgeted, nothing done: no row of zeros. The course says the
  // budget is the next step.
  if (!totals.budgeted_cents && !totals.realised_total_cents && nothingPlanned(totals)) return null;
  const figures: KeyFigure[] = [
    { label: FIGURE_LABELS.budgeted, value: formatEuro(totals.budgeted_cents) },
    { label: FIGURE_LABELS.realised, value: formatEuro(totals.realised_total_cents) },
    // Without inzet there is no expected total; say that, not "100% ruimte".
    ...(nothingPlanned(totals)
      ? [{ label: FIGURE_LABELS.expected, value: NOTHING_PLANNED_TEXT }]
      : [
          { label: FIGURE_LABELS.expected, value: formatEuro(totals.expected_total_cents) },
          {
            label: FIGURE_LABELS.variance,
            value: varianceText(totals),
            detail: varianceWord(totals),
            critical: totals.overrun,
          },
        ]),
  ];
  return <KeyFigures label="Kerncijfers over de hele looptijd" figures={figures} />;
}

/**
 * Steps that are one decision and nothing more: the head does them in place,
 * by the kind of work the server names, to the status they lead to.
 */
const IN_PLACE: Record<string, readonly string[]> = {
  'uitvoering.starten': ['in_progress'],
  // An internal assignment has no quote and no agreement to wait for:
  // starting it takes both status steps at once.
  'intern.starten': ['accepted', 'in_progress'],
};

/**
 * The frame around every page of one assignment: a compact header and the
 * tabs. Each tab is one concern, so money and people never share a table.
 */
export function AssignmentLayout() {
  const { assignmentId = '' } = useParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const instance = useInstance();
  const query = useQuery({
    queryKey: assignmentKeys.detail(assignmentId),
    queryFn: () => fetchAssignment(assignmentId),
    enabled: assignmentId !== '',
    retry: false,
  });
  const assignment = query.data;
  // One quiet line: for whom, when, and as who the reader looks.
  const facts = assignment
    ? [
        // Said in words: a tag would pull the eye from the sentence and the one action.
        assignment.phase === 'potential' ? 'Potentiële opdracht' : '',
        assignment.client_name,
        formatPeriod(assignment.start_date, assignment.end_date),
        // The page is the assignment; the line need not name it again.
        relationText(assignment.viewer_relations)
          .replace(' van deze opdracht', '')
          .replace(' deze opdracht', '')
          .replace(/\.$/, ''),
      ]
        .filter(Boolean)
        .join(' · ')
    : '';

  const tabs = assignment ? visibleTabs(assignment.permissions) : [];
  // Where the assignment stands and what is next, from the same facts as
  // its tasks. The step is the page's one primary action, unless the reader
  // already is where it is done: there the page's own button does it.
  const course = useCaseCourse('assignment', assignmentId, assignment !== undefined).data?.course;
  const next = courseAction(course);
  const here = pathname.replace(/\/$/, '');
  const path = course?.next?.mine ? IN_PLACE[course.next.task_key ?? ''] : undefined;
  // The status steps still to take: from the first one the assignment may take now.
  const from = path?.findIndex((status) =>
    (assignment?.allowed_transitions ?? []).includes(status),
  );
  const target = path && from !== undefined && from >= 0 ? path.slice(from) : undefined;
  const allowed = target !== undefined;
  const elsewhere =
    next && (allowed || next.href.split('?')[0]?.replace(/\/$/, '') !== here) ? next : null;
  const queryClient = useQueryClient();
  const [problem, setProblem] = useState<string | null>(null);
  const step = useMutation({
    mutationFn: async (statuses: readonly string[]) => {
      for (const status of statuses) await transitionAssignment(assignmentId, status);
    },
    onSuccess: () => {
      setProblem(null);
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.all });
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
    },
    onError: (error) => setProblem(errorMessage(error)),
  });
  return (
    <>
      <ThingHead
        title={assignment?.name ?? 'Opdracht'}
        instanceName={instance?.name}
        back={{ href: PATHS.assignments, text: 'Terug naar Opdrachten' }}
        {...(elsewhere
          ? {
              action: (
                <Button
                  appearance="primary"
                  text={elsewhere.text}
                  loading={step.isPending}
                  onClick={() =>
                    allowed && target ? step.mutate(target) : navigate(elsewhere.href)
                  }
                />
              ),
            }
          : {})}
        {...(assignment
          ? {
              tabs: {
                label: `Onderdelen van ${assignment.name}`,
                current: currentTab(assignment.id, pathname, tabs) ?? '',
                items: tabs.map((tab) => ({
                  key: tab,
                  text: TAB_LABELS[tab],
                  href: assignmentTabPath(assignment.id, tab),
                })),
              },
            }
          : {})}
      >
        {query.isPending && <Loading />}
        {query.isError && (
          <LoadError error={query.error} retry={() => void query.refetch()} what="Deze opdracht" />
        )}
        {problem && <ErrorNotice message={problem} />}
        {assignment && (
          <>
            {course && (
              <CourseNow course={course} tasksHref={assignmentTabPath(assignment.id, 'tasks')} />
            )}
            <TakeOverButton course={course} />
            {course && !course.ended && (
              <CourseBar course={course} accessibleLabel={`Verloop van ${assignment.name}`} />
            )}
            <nldd-container layout="wrap" gap="8" vertical-alignment="center">
              {/* The course says where it stands; the status only once it has ended. */}
              {(!course || course.ended) && (
                <nldd-badge
                  color={STATUS_COLORS[assignment.status] ?? 'neutral'}
                  text={course?.ended ?? statusLabel(assignment.status)}
                />
              )}
              {facts && <nldd-text color="secondary">{facts}</nldd-text>}
            </nldd-container>
            {assignment.permissions.read_financial && <Figures assignment={assignment} />}
          </>
        )}
      </ThingHead>
      {assignment && (
        <AssignmentShellContext.Provider value={assignment}>
          <PrimaryTakenContext.Provider value={elsewhere !== null}>
            <Outlet />
          </PrimaryTakenContext.Provider>
        </AssignmentShellContext.Provider>
      )}
    </>
  );
}
