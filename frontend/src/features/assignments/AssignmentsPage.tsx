import { standingText, useCourses } from '@/features/tasks/course';
import { LoadError, Page, Stack } from '@/ui/layout';
import { useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { clientAssignmentPath } from '@/features/client/paths';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatEuro, formatPeriod } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import { Button } from '@/ui/Button';
import { LinkRows, type LinkRow } from '@/ui/LinkRows';
import { PageRange, Pager } from '@/ui/Pager';
import { usePaging, useSearchWords } from '@/ui/paging';
import {
  ASSIGNMENT_PAGE_SIZE,
  assignmentKeys,
  fetchAssignments,
  type AssignmentSummary,
} from './api';
import { AssignmentFormSheet } from './AssignmentFormSheet';
import { PHASE_VIEW_LABELS, STATUS_COLORS, statusLabel, type Phase } from './labels';
import { assignmentPath } from './paths';
import { EmptyNotice, Loading } from './ui';
import { SEARCH_PARAM, VIEWS, VIEW_PARAM, phaseOfView, viewHref } from './views';

const EMPTY_TEXT: Record<Phase, { text: string; supporting: string }> = {
  potential: {
    text: 'Er zijn geen potentiële opdrachten',
    supporting: 'Een nieuwe opdracht begint hier, tot de opdrachtgever akkoord geeft.',
  },
  active: {
    text: 'Er zijn geen lopende opdrachten',
    supporting: 'Je ziet hier de opdrachten met akkoord waar je bij betrokken bent.',
  },
  closed: {
    text: 'Er zijn geen afgesloten opdrachten',
    supporting: 'Afgeronde en geannuleerde opdrachten komen hier te staan.',
  },
};

/** The status a view implies; a row names its status only when it says more. */
const VIEW_DEFAULT_STATUS: Record<Phase, string | undefined> = {
  potential: undefined,
  active: 'in_progress',
  closed: 'completed',
};

const AMOUNT_SOURCE = {
  quote: 'bedrag uit de laatste offerte',
  budget: 'bedrag uit de begroting, nog geen offerte',
} as const;

type Courses = ReturnType<typeof useCourses>['byId'];

/** One assignment as a row: what it is, for whom and when, and where it stands. */
function rowOf(item: AssignmentSummary, phase: Phase, courses: Courses): LinkRow {
  const amount =
    item.pipeline_amount_cents == null ? undefined : formatEuro(item.pipeline_amount_cents);
  const source =
    amount && item.pipeline_amount_source ? AMOUNT_SOURCE[item.pipeline_amount_source] : undefined;
  const notice = [
    item.client_name,
    formatPeriod(item.start_date, item.end_date),
    standingText(courses.get(item.id)?.course),
    source,
  ]
    .filter(Boolean)
    .join(' · ');
  return {
    key: item.id,
    text: item.name,
    href: item.as_client ? clientAssignmentPath(item.id) : assignmentPath(item.id),
    ...(notice ? { notice } : {}),
    ...(item.status !== VIEW_DEFAULT_STATUS[phase]
      ? { tag: { text: statusLabel(item.status), color: STATUS_COLORS[item.status] ?? 'neutral' } }
      : {}),
    ...(amount ? { end: amount } : {}),
  };
}

function AssignmentRows({
  items,
  label,
  phase,
}: {
  items: AssignmentSummary[];
  label: string;
  phase: Phase;
}) {
  const courses = useCourses(
    'assignment',
    items.map((item) => item.id),
  ).byId;
  return <LinkRows label={label} rows={items.map((item) => rowOf(item, phase, courses))} />;
}

/** The assignments in three views: pipeline, running work, and what is closed. */
export function AssignmentsPage() {
  const instance = useInstance();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [searchParams] = useSearchParams();
  const [sheet, setSheet] = useState({ open: false, session: 0 });
  const contentRef = useRef<HTMLDivElement>(null);
  useRouterLinks(contentRef);

  const phase = phaseOfView(searchParams.get(VIEW_PARAM));
  const [words, setWords, search] = useSearchWords(SEARCH_PARAM);
  // The server sends one page of one view, and counts all three.
  const asked = usePaging(undefined, ASSIGNMENT_PAGE_SIZE).page;
  const query = useQuery({
    queryKey: assignmentKeys.list({ phase, page: asked, search }),
    queryFn: () => fetchAssignments({ phase, page: asked, search }),
    // The rows stay while the next page or the next search is on its way.
    placeholderData: keepPreviousData,
  });
  const paging = usePaging(query.data?.total, ASSIGNMENT_PAGE_SIZE);
  const items = query.data?.items ?? [];
  const counts = query.data?.counts;
  const empty = search
    ? {
        text: `Geen opdrachten gevonden voor "${search}"`,
        supporting: 'Je zoekt op de naam van de opdracht of van de opdrachtgever.',
      }
    : EMPTY_TEXT[phase];

  return (
    <Page
      kind="list"
      title="Opdrachten"
      instanceName={instance?.name}
      action={
        query.data?.can_create ? (
          <Button
            text="Nieuwe opdracht"
            appearance="primary"
            onClick={() => setSheet((current) => ({ open: true, session: current.session + 1 }))}
          />
        ) : undefined
      }
      // Each view has its own address, so this is navigation between pages.
      tabs={{
        label: 'Weergave van de opdrachten',
        current: phase,
        narrow: 'bar',
        items: VIEWS.map((view) => ({
          key: view.phase,
          href: viewHref(pathname, view.phase, search),
          text: counts
            ? `${PHASE_VIEW_LABELS[view.phase]} (${counts[view.phase]})`
            : PHASE_VIEW_LABELS[view.phase],
          short: PHASE_VIEW_LABELS[view.phase],
        })),
      }}
    >
      <div ref={contentRef}>
        <Stack gap="group">
          <ActionBar
            label="Opdrachten zoeken"
            search={{
              label: 'Zoek op opdracht of opdrachtgever',
              value: words,
              onChange: setWords,
            }}
          />
          {query.isPending && <Loading />}
          {query.isError && <LoadError error={query.error} retry={() => void query.refetch()} />}
          {query.isSuccess && items.length === 0 && (
            <EmptyNotice text={empty.text} supportingText={empty.supporting} />
          )}
          {items.length > 0 && (
            <Stack gap="related">
              <PageRange paging={paging} noun="opdrachten" />
              <AssignmentRows items={items} label={PHASE_VIEW_LABELS[phase]} phase={phase} />
              <Pager paging={paging} label="Pagina's van de opdrachten" />
            </Stack>
          )}
        </Stack>
      </div>
      {/* The form asks for what it offers (the organisations): only once it is opened. */}
      {sheet.session > 0 && (
        <AssignmentFormSheet
          open={sheet.open}
          session={sheet.session}
          onClose={() => setSheet((current) => ({ ...current, open: false }))}
          onSaved={(saved) => {
            setSheet((current) => ({ ...current, open: false }));
            navigate(assignmentPath(saved.id));
          }}
        />
      )}
    </Page>
  );
}
