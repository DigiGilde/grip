import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Outlet, useLocation, useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { orUndef } from '@/components/nldd/events';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatEuro, formatPeriod } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { Quiet, Stack } from '@/ui/layout';
import { PATHS } from '@/paths';
import { assignmentKeys, fetchAssignment, type AssignmentDetail } from './api';
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
import { ErrorNotice, Loading } from './ui';

/** Spread as plain attributes; the package types do not list the padding overrides. */
const HEADER_PADDING: object = { 'padding-bottom': '0' };

/** The whole period: the header never follows a year filter on a tab. */
const WHOLE_PERIOD = 'all';

function currentTab(id: string, pathname: string, tabs: AssignmentTabKey[]): AssignmentTabKey {
  const path = pathname.replace(/\/$/, '');
  return (
    tabs.find((tab) => tab !== 'overview' && path.startsWith(assignmentTabPath(id, tab))) ??
    'overview'
  );
}

/** Begroot, gerealiseerd, verwacht totaal and the variance, for who may see money. */
function KeyFigures({ assignment }: { assignment: AssignmentDetail }) {
  const query = useQuery({
    queryKey: financeKeys.assignment(assignment.id, WHOLE_PERIOD),
    queryFn: () => fetchAssignmentFinance(assignment.id, WHOLE_PERIOD),
  });
  const totals = query.data?.totals;
  if (!totals) return null;
  return (
    <nldd-table accessible-label="Kerncijfers over de hele looptijd" columns="repeat(4, minmax(130px, 1fr))">
      <nldd-table-row slot="header">
        <nldd-text-cell text={FIGURE_LABELS.budgeted} horizontal-alignment="right" />
        <nldd-text-cell text={FIGURE_LABELS.realised} horizontal-alignment="right" />
        <nldd-text-cell text={FIGURE_LABELS.expected} horizontal-alignment="right" />
        <nldd-text-cell text={FIGURE_LABELS.variance} horizontal-alignment="right" />
      </nldd-table-row>
      <nldd-table-row>
        <nldd-text-cell text={formatEuro(totals.budgeted_cents)} horizontal-alignment="right" />
        <nldd-text-cell
          text={formatEuro(totals.realised_total_cents)}
          horizontal-alignment="right"
        />
        {nothingPlanned(totals) ? (
          // Without inzet there is no expected total; say that, not "100% ruimte".
          <>
            <nldd-text-cell text={NOTHING_PLANNED_TEXT} horizontal-alignment="right" />
            <nldd-text-cell />
          </>
        ) : (
          <>
            <nldd-text-cell
              text={formatEuro(totals.expected_total_cents)}
              horizontal-alignment="right"
            />
            <nldd-text-cell
              text={varianceText(totals)}
              supporting-text={varianceWord(totals)}
              horizontal-alignment="right"
              {...(totals.overrun ? { color: 'critical' } : {})}
            />
          </>
        )}
      </nldd-table-row>
    </nldd-table>
  );
}

function Tabs({ assignment }: { assignment: AssignmentDetail }) {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  useRouterLinks(ref);
  const tabs = visibleTabs(assignment.permissions);
  const current = currentTab(assignment.id, pathname, tabs);
  // Each tab is a page with its own address, so this is navigation: the
  // design system then renders a nav landmark and marks the current page.
  return (
    <nldd-tab-bar ref={ref} navigation accessible-label={`Onderdelen van ${assignment.name}`}>
      {tabs.map((tab) => (
        <nldd-tab-bar-item
          key={tab}
          href={assignmentTabPath(assignment.id, tab)}
          text={TAB_LABELS[tab]}
          current={orUndef(tab === current)}
        />
      ))}
    </nldd-tab-bar>
  );
}

/**
 * The frame around every page of one assignment: a compact header and the
 * tabs. Each tab is one concern, so money and people never share a table.
 */
export function AssignmentLayout() {
  const { assignmentId = '' } = useParams();
  const instance = useInstance();
  const query = useQuery({
    queryKey: assignmentKeys.detail(assignmentId),
    queryFn: () => fetchAssignment(assignmentId),
    enabled: assignmentId !== '',
    retry: false,
  });
  const assignment = query.data;
  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const facts = assignment
    ? [assignment.client_name, formatPeriod(assignment.start_date, assignment.end_date)]
        .filter(Boolean)
        .join(', ')
    : '';

  const relation = relationText(assignment?.viewer_relations);

  return (
    <>
      {/* The tab below is a section of its own with its own top padding;
          without a bottom padding here the two would add up under the tabs. */}
      <nldd-simple-section {...HEADER_PADDING}>
        <PageHeading text={assignment?.name ?? 'Opdracht'} instanceName={instance?.name} />
        <Stack gap="related">
          <RouterLinks>
            <nldd-link href={PATHS.assignments} text="Terug naar opdrachten" size="md" />
          </RouterLinks>
          {query.isPending && <Loading />}
          {query.isError && (
            <ErrorNotice
              message={
                notFound
                  ? 'Deze opdracht bestaat niet, of je hebt er geen toegang toe.'
                  : errorMessage(query.error)
              }
            />
          )}
          {assignment && (
            <>
              <nldd-container layout="row" gap="8">
                {assignment.phase === 'potential' && (
                  <nldd-badge color="warning" text="Potentiële opdracht" />
                )}
                <nldd-badge
                  color={STATUS_COLORS[assignment.status] ?? 'neutral'}
                  text={statusLabel(assignment.status)}
                />
              </nldd-container>
              {facts && <nldd-text color="secondary">{facts}</nldd-text>}
              {relation && <Quiet>{relation}</Quiet>}
              {assignment.permissions.read_financial && <KeyFigures assignment={assignment} />}
              <Tabs assignment={assignment} />
            </>
          )}
        </Stack>
      </nldd-simple-section>
      {assignment && (
        <AssignmentShellContext.Provider value={assignment}>
          <Outlet />
        </AssignmentShellContext.Provider>
      )}
    </>
  );
}
