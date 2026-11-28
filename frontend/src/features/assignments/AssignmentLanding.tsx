import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { chronicleKeys } from '@/features/chronicle/api';
import { incompleteText } from '@/features/costs/costText';
import { TakeOverButton } from '@/features/tasks/TakeOver';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { formatEuro, formatPeriod } from '@/lib/format';
import { PATHS } from '@/paths';
import { Button } from '@/ui/Button';
import { courseAction, courseBrief, lowerFirst, type Course } from '@/ui/course';
import { ErrorNotice, Page, Quiet, Stack } from '@/ui/layout';
import { LinkRows } from '@/ui/LinkRows';
import { CourseBar, CourseNow } from '@/ui/Workflow';
import { assignmentKeys, transitionAssignment, type AssignmentDetail } from './api';
import { fetchAssignmentFinance, financeKeys, type Figures as Totals } from './financeApi';
import {
  FIGURE_LABELS,
  NOTHING_PLANNED_TEXT,
  nothingPlanned,
  varianceText,
  varianceWord,
} from './financeText';
import { statusLabel } from './labels';
import type { AssignmentParts } from './partsApi';
import { assignmentPartPath, assignmentPath } from './paths';
import { useAssignmentFrame, useAssignmentShell } from './shell';

/** The whole period: the landing never follows a year filter on a part. */
const WHOLE_PERIOD = 'all';

/**
 * Steps that are one decision and nothing more: the landing does them in
 * place, by the kind of work the server names, to the status they lead to.
 */
const IN_PLACE: Record<string, string> = {
  'uitvoering.starten': 'in_progress',
  // An internal assignment has no quote and no agreement to wait for.
  'intern.starten': 'in_progress',
};

/** For whom and when, and where it stands when the course bar does not say it. */
function factsLine(assignment: AssignmentDetail, course: Course | null | undefined): string {
  const facts = [
    assignment.client_name,
    formatPeriod(assignment.start_date, assignment.end_date),
  ].filter(Boolean);
  const brief = course ? courseBrief(course) : null;
  // "Afgerond" says there is nothing left; a step still open says otherwise.
  const standing =
    assignment.status === 'completed' && course?.next
      ? 'Werk afgerond, afsluiten loopt nog'
      : statusLabel(assignment.status);
  return [
    // Said in words: a tag would pull the eye from the sentence and the one action.
    assignment.phase === 'potential' ? 'Potentiële opdracht' : '',
    facts.join(', '),
    course?.ended ?? (brief ? '' : standing),
  ]
    .filter(Boolean)
    .map((sentence) => `${sentence}.`)
    .join(' ');
}

function Figure({ label, value, critical }: { label: string; value: string; critical?: boolean }) {
  return (
    <nldd-container gap="4">
      <nldd-text size="sm">
        <span>{label}</span>
      </nldd-text>
      <nldd-text weight="bold" {...(critical ? { color: 'critical' } : {})}>
        <span>{value}</span>
      </nldd-text>
    </nldd-container>
  );
}

function Figures({ totals, incompleteBy }: { totals: Totals; incompleteBy: readonly string[] }) {
  // A new assignment has figures of zero, not absent ones: zero on all three
  // is "nothing yet". The course says the budget is the next step.
  if (!totals.budgeted_cents && !totals.realised_total_cents && !totals.expected_total_cents) {
    return null;
  }
  const figures = (
    <nldd-container
      layout="grid"
      column-count={3}
      gap="16"
      role="group"
      aria-label="Kerncijfers over de hele looptijd"
    >
      <Figure label={FIGURE_LABELS.budgeted} value={formatEuro(totals.budgeted_cents)} />
      {/* Without inzet there is no expected total; say that, not "100% ruimte". */}
      {nothingPlanned(totals) ? (
        <Figure label={FIGURE_LABELS.expected} value={NOTHING_PLANNED_TEXT} />
      ) : (
        <>
          <Figure label={FIGURE_LABELS.expected} value={formatEuro(totals.expected_total_cents)} />
          <Figure
            label={FIGURE_LABELS.variance}
            value={`${varianceText(totals)} ${lowerFirst(varianceWord(totals))}`}
            critical={totals.overrun}
          />
        </>
      )}
    </nldd-container>
  );
  if (incompleteBy.length === 0) return figures;
  return (
    <Stack gap="close">
      {figures}
      <Quiet>{incompleteText(incompleteBy)}</Quiet>
    </Stack>
  );
}

interface LandingProps {
  assignment: AssignmentDetail;
  parts: AssignmentParts;
  course: Course | null | undefined;
}

function Landing({ assignment, parts, course }: LandingProps) {
  const instance = useInstance();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [problem, setProblem] = useState<string | null>(null);
  const finance = useQuery({
    queryKey: financeKeys.assignment(assignment.id, WHOLE_PERIOD),
    queryFn: () => fetchAssignmentFinance(assignment.id, WHOLE_PERIOD),
    enabled: assignment.permissions.read_financial && !parts.is_client,
  });
  const step = useMutation({
    mutationFn: (status: string) => transitionAssignment(assignment.id, status),
    onSuccess: () => {
      setProblem(null);
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.all });
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
      void queryClient.invalidateQueries({ queryKey: chronicleKeys.moments(assignment.id) });
    },
    onError: (error) => setProblem(errorMessage(error)),
  });

  const action = courseAction(course);
  const leadsTo = course?.next?.mine ? IN_PLACE[course.next.task_key ?? ''] : undefined;
  const inPlace = leadsTo && assignment.allowed_transitions.includes(leadsTo) ? leadsTo : null;
  const here = assignmentPath(assignment.id);
  const leads = action !== null && (inPlace !== null || action.href.split('?')[0] !== here);
  const tasksHref = parts.tasks_link ? assignmentPartPath(assignment.id, 'tasks') : null;
  // "En nog N taken voor jou" is the link to the tasks when there is such a line.
  const moreLinked =
    tasksHref !== null && course && !course.ended && course.next && (course.more_to_do ?? 0) > 0;

  return (
    <Page
      kind="list"
      title={assignment.name}
      lead={factsLine(assignment, course)}
      instanceName={instance?.name}
      back={{ href: PATHS.assignments, text: 'Terug naar Opdrachten' }}
      action={
        leads ? (
          <Button
            appearance="primary"
            text={action.text}
            loading={step.isPending}
            onClick={() => (inPlace ? step.mutate(inPlace) : navigate(action.href))}
          />
        ) : undefined
      }
    >
      {problem && <ErrorNotice message={problem} />}
      <Stack gap="related">
        {course && (
          <RouterLinks>
            <CourseNow course={course} {...(tasksHref ? { tasksHref } : {})} />
          </RouterLinks>
        )}
        {course && !course.ended && (
          <CourseBar course={course} accessibleLabel={`Verloop van ${assignment.name}`} />
        )}
        <TakeOverButton course={course} />
      </Stack>
      {/* The figures take room when they come: the rows wait, so they do not jump. */}
      {!finance.isLoading && (
        <Stack gap="related">
          {finance.data?.totals && (
            <Figures totals={finance.data.totals} incompleteBy={finance.data.incomplete_by} />
          )}
          {tasksHref && !moreLinked && (
            <RouterLinks>
              <div>
                <nldd-link size="sm" href={tasksHref} text="Alle taken van deze opdracht" />
              </div>
            </RouterLinks>
          )}
          {parts.own_line && (
            <nldd-text>
              <p>{`Jij: ${parts.own_line}`}</p>
            </nldd-text>
          )}
          <LinkRows
            label={`Onderdelen van ${assignment.name}`}
            rows={parts.parts.map((part) => ({
              key: part.key,
              text: part.label,
              ...(part.notice ? { notice: part.notice } : {}),
              href: assignmentPartPath(assignment.id, part.key),
            }))}
          />
        </Stack>
      )}
    </Page>
  );
}

/** Where an assignment opens: what is next, the key figures and its parts as rows. */
export function AssignmentLanding() {
  const assignment = useAssignmentShell();
  const frame = useAssignmentFrame();
  if (!assignment || !frame) return null;
  return <Landing assignment={assignment} parts={frame.parts} course={frame.course} />;
}
