import { useMemo, useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { useAuth } from '@/auth/context';
import { useInstance } from '@/layout/useInstance';
import { ActionBar } from '@/ui/ActionBar';
import { EmptyNotice, ErrorNotice, Loading, Page, Stack } from '@/ui/layout';
import { HISTORY_KEYS, fetchEvents, fetchKinds, type CaseKind, type EventFilters } from './api';
import { KIND_LABELS, formatMoment, moments } from './words';

/**
 * What happened, newest first: when, what, and who did it. One row per
 * action; what may not be seen is not there.
 */
function HistoryList({ filters, label }: { filters: EventFilters; label: string }) {
  const query = useInfiniteQuery({
    queryKey: HISTORY_KEYS.list(filters),
    queryFn: ({ pageParam }) => fetchEvents(filters, pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_before ?? undefined,
  });
  const rows = useMemo(
    () => moments(query.data?.pages.flatMap((page) => page.items) ?? []),
    [query.data],
  );
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  if (rows.length === 0 && !query.hasNextPage) return <EmptyNotice text="Nog niets gebeurd" />;
  return (
    <Stack gap="related">
      <nldd-table
        accessible-label={label}
        columns="170px minmax(260px,3fr) minmax(140px,1fr)"
        sm-columns="minmax(0,1fr)"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Wanneer" hide-below="md" />
          <nldd-text-cell text="Wat" />
          <nldd-text-cell text="Door" hide-below="md" />
        </nldd-table-row>
        {rows.map((row) => (
          <nldd-table-row key={row.key}>
            <nldd-text-cell hide-below="md" text={formatMoment(row.occurred_at)} />
            <nldd-text-cell
              hide-below="md"
              text={row.headline}
              supporting-text={row.lines.join(' · ')}
            />
            {/* Narrow: when and who read above and below the one column. */}
            <nldd-text-cell
              hide-above="sm"
              overline={`${formatMoment(row.occurred_at)} · ${row.actor}`}
              text={row.headline}
              supporting-text={row.lines.join(' · ')}
            />
            <nldd-text-cell hide-below="md" text={row.actor} />
          </nldd-table-row>
        ))}
      </nldd-table>
      {query.hasNextPage && (
        <ActionBar
          label="Verder terug"
          filters={[]}
          actions={[
            {
              text: 'Toon eerder',
              onClick: () => void query.fetchNextPage(),
              loading: query.isFetchingNextPage,
            },
          ]}
        />
      )}
    </Stack>
  );
}

/** The history of one case. */
export function CaseHistory({ kind, caseId }: { kind: CaseKind; caseId: string }) {
  const filters = useMemo(() => ({ case_kind: kind, case_id: caseId }), [kind, caseId]);
  if (caseId === '') return null;
  return (
    <nldd-simple-section>
      <HistoryList filters={filters} label="Geschiedenis" />
    </nldd-simple-section>
  );
}

/** The tab "Geschiedenis" of an assignment. */
export function AssignmentHistoryTab() {
  const { assignmentId = '' } = useParams();
  return <CaseHistory kind="assignment" caseId={assignmentId} />;
}

/** The tab "Geschiedenis" of a vacancy. */
export function VacancyHistoryTab() {
  const { vacancyId = '' } = useParams();
  return <CaseHistory kind="vacancy" caseId={vacancyId} />;
}

const ALL = 'all';

const PERIODS: { value: string; label: string; days?: number }[] = [
  { value: ALL, label: 'Alles' },
  { value: '1', label: 'Vandaag', days: 1 },
  { value: '7', label: 'Afgelopen week', days: 7 },
  { value: '30', label: 'Afgelopen maand', days: 30 },
  { value: '365', label: 'Afgelopen jaar', days: 365 },
];

function startOf(days: number): string {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - (days - 1));
  return start.toISOString();
}

/** Everything that happened in the instance, for the beheerder. */
export function ActivityPage() {
  const instance = useInstance();
  const { state } = useAuth();
  const isAdmin = state.status === 'authenticated' && state.functions.includes('beheerder');
  const [kind, setKind] = useState(ALL);
  const [period, setPeriod] = useState(ALL);
  const kinds = useQuery({ queryKey: HISTORY_KEYS.kinds, queryFn: fetchKinds, enabled: isAdmin });

  const filters = useMemo<EventFilters>(() => {
    const days = PERIODS.find((option) => option.value === period)?.days;
    return {
      ...(kind !== ALL ? { subject_kind: kind } : {}),
      ...(days ? { since: startOf(days) } : {}),
    };
  }, [kind, period]);

  const kindOptions = useMemo(
    () => [
      { value: ALL, label: 'Alles' },
      ...(kinds.data ?? [])
        .filter((value) => KIND_LABELS[value])
        .map((value) => ({ value, label: KIND_LABELS[value]! }))
        .sort((a, b) => a.label.localeCompare(b.label, 'nl')),
    ],
    [kinds.data],
  );

  return (
    <Page title="Activiteit" instanceName={instance?.name}>
      {isAdmin ? (
        <>
          <ActionBar
            label="Activiteit filteren"
            filters={[
              {
                label: 'Soort',
                value: kind,
                onChange: setKind,
                options: kindOptions,
                width: '260px',
              },
              {
                label: 'Periode',
                value: period,
                onChange: setPeriod,
                options: PERIODS,
                width: '200px',
              },
            ]}
            actions={[]}
          />
          <HistoryList filters={filters} label="Activiteit" />
        </>
      ) : (
        <EmptyNotice text="Activiteit is voor beheerders" />
      )}
    </Page>
  );
}
