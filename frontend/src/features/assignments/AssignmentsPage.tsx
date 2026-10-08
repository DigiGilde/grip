import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { orUndef } from '@/components/nldd/events';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatEuro, formatPeriod } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { ActionBar } from '@/ui/ActionBar';
import { assignmentKeys, fetchAssignments, type AssignmentSummary } from './api';
import { AssignmentFormSheet } from './AssignmentFormSheet';
import { PHASE_VIEW_LABELS, STATUS_COLORS, statusLabel, type Phase } from './labels';
import { assignmentPath } from './paths';
import { EmptyNotice, ErrorNotice, Loading } from './ui';
import {
  VIEWS,
  VIEW_PARAM,
  countByPhase,
  daysSince,
  durationText,
  phaseOfView,
  viewHref,
} from './views';

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
    supporting: 'Afgeronde, afgewezen en geannuleerde opdrachten komen hier te staan.',
  },
};

function NameCell({ item }: { item: AssignmentSummary }) {
  return (
    <nldd-cell>
      <nldd-link href={assignmentPath(item.id)} text={item.name} />
    </nldd-cell>
  );
}

function StatusCell({ item }: { item: AssignmentSummary }) {
  return (
    <nldd-cell>
      <nldd-badge color={STATUS_COLORS[item.status] ?? 'neutral'} text={statusLabel(item.status)} />
    </nldd-cell>
  );
}

/** What an account manager needs: client, where it stands, what it may be worth, how long. */
function PipelineTable({ items }: { items: AssignmentSummary[] }) {
  const showAmounts = items.some((item) => 'pipeline_amount_cents' in item);
  return (
    <nldd-table
      accessible-label="Potentiële opdrachten"
      columns={`minmax(220px,2fr) minmax(160px,1fr) 190px${showAmounts ? ' 170px' : ''} 150px`}
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Potentiële opdracht" />
        <nldd-text-cell text="Opdrachtgever" />
        <nldd-text-cell text="Stand" />
        {showAmounts && <nldd-text-cell text="Bedrag" horizontal-alignment="right" />}
        <nldd-text-cell text="In deze stand sinds" />
      </nldd-table-row>
      {items.map((item) => (
        <nldd-table-row key={item.id}>
          <NameCell item={item} />
          <nldd-text-cell text={item.client_name ?? ''} />
          <StatusCell item={item} />
          {showAmounts && (
            <nldd-text-cell
              text={
                item.pipeline_amount_cents == null
                  ? 'Nog geen bedrag'
                  : formatEuro(item.pipeline_amount_cents)
              }
              {...(item.pipeline_amount_source
                ? {
                    'supporting-text':
                      item.pipeline_amount_source === 'quote'
                        ? 'Laatste offerte'
                        : 'Begroting, nog geen offerte',
                  }
                : {})}
              horizontal-alignment="right"
            />
          )}
          <nldd-text-cell text={durationText(daysSince(item.status_since))} />
        </nldd-table-row>
      ))}
    </nldd-table>
  );
}

function AssignmentTable({ items, label }: { items: AssignmentSummary[]; label: string }) {
  return (
    <nldd-table
      accessible-label={label}
      columns="minmax(220px,2fr) 170px minmax(160px,1fr) minmax(200px,1fr) minmax(140px,1fr)"
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Opdracht" />
        <nldd-text-cell text="Status" />
        <nldd-text-cell text="Opdrachtgever" />
        <nldd-text-cell text="Periode" />
        <nldd-text-cell text="Eigenaar" />
      </nldd-table-row>
      {items.map((item) => (
        <nldd-table-row key={item.id}>
          <NameCell item={item} />
          <StatusCell item={item} />
          <nldd-text-cell text={item.client_name ?? ''} />
          <nldd-text-cell text={formatPeriod(item.start_date, item.end_date)} />
          <nldd-text-cell text={item.owner_name ?? ''} />
        </nldd-table-row>
      ))}
    </nldd-table>
  );
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

  const query = useQuery({ queryKey: assignmentKeys.list(), queryFn: fetchAssignments });
  const all = query.data?.items ?? [];
  const phase = phaseOfView(searchParams.get(VIEW_PARAM));
  const counts = countByPhase(all);
  const items = all.filter((item) => item.phase === phase);

  return (
    <nldd-simple-section>
      <PageHeading text="Opdrachten" instanceName={instance?.name} />
      <div ref={contentRef}>
        <nldd-container gap="16">
          {query.data?.can_create && (
            <ActionBar
              label="Opdrachten"
              actions={[
                {
                  text: 'Nieuwe opdracht',
                  primary: true,
                  onClick: () => setSheet((current) => ({ open: true, session: current.session + 1 })),
                },
              ]}
            />
          )}
          {/* Each view has its own address, so this is navigation between pages. */}
          <nldd-tab-bar navigation accessible-label="Weergave van de opdrachten">
            {VIEWS.map((view) => (
              <nldd-tab-bar-item
                key={view.phase}
                href={viewHref(pathname, view.phase)}
                text={
                  query.isSuccess
                    ? `${PHASE_VIEW_LABELS[view.phase]} (${counts[view.phase]})`
                    : PHASE_VIEW_LABELS[view.phase]
                }
                current={orUndef(view.phase === phase)}
              />
            ))}
          </nldd-tab-bar>
          {query.isPending && <Loading />}
          {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
          {query.isSuccess && items.length === 0 && (
            <EmptyNotice
              text={EMPTY_TEXT[phase].text}
              supportingText={EMPTY_TEXT[phase].supporting}
            />
          )}
          {items.length > 0 &&
            (phase === 'potential' ? (
              <PipelineTable items={items} />
            ) : (
              <AssignmentTable items={items} label={PHASE_VIEW_LABELS[phase]} />
            ))}
        </nldd-container>
      </div>
      <AssignmentFormSheet
        open={sheet.open}
        session={sheet.session}
        onClose={() => setSheet((current) => ({ ...current, open: false }))}
        onSaved={(saved) => {
          setSheet((current) => ({ ...current, open: false }));
          navigate(assignmentPath(saved.id));
        }}
      />
    </nldd-simple-section>
  );
}
