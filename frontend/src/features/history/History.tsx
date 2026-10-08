import { useEffect, useMemo, useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { useAuth } from '@/auth/context';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { Button } from '@/features/team/ui/controls';
import { ActionBar } from '@/ui/ActionBar';
import { EmptyNotice, ErrorNotice, Loading, Page, Quiet, Stack } from '@/ui/layout';
import {
  HISTORY_KEYS,
  PAGE_SIZE,
  fetchEvents,
  fetchKinds,
  type CaseKind,
  type EventFilters,
} from './api';
import { KIND_LABELS, formatMoment, moments, type Moment } from './words';

/** How many lines of an action show before the reader asks for the rest. */
const SHOWN = 3;

/** What one action changed: a few lines, the rest on request. */
function MomentLines({ row }: { row: Moment }) {
  const [open, setOpen] = useState(false);
  const lines = open ? row.lines : row.lines.slice(0, SHOWN);
  const rest = row.lines.length - SHOWN;
  return (
    <nldd-container gap="4">
      <nldd-text size="md">{row.headline}</nldd-text>
      {lines.map((line) => (
        <nldd-text key={line} size="sm" color="secondary">
          {line}
        </nldd-text>
      ))}
      {rest > 0 && (
        <nldd-container layout="row">
          <Button
            text={open ? 'Toon minder' : `Toon alle ${row.lines.length} wijzigingen`}
            size="sm"
            appearance="neutral-transparent"
            onClick={() => setOpen((value) => !value)}
          />
        </nldd-container>
      )}
    </nldd-container>
  );
}

/** Rows wanted on screen before the reader has to ask for older ones. */
const WANTED = 15;
/** Pages read in one go while looking for them. */
const MAX_AUTO_PAGES = 6;

/**
 * What happened, newest first: when, what, and who did it. One row per
 * action; what may not be seen is not there.
 */
function HistoryList({
  filters,
  label,
  show = 'all',
}: {
  filters: EventFilters;
  label: string;
  show?: 'all' | 'changes';
}) {
  const query = useInfiniteQuery({
    queryKey: HISTORY_KEYS.list(filters),
    queryFn: ({ pageParam }) => fetchEvents(filters, pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_before ?? undefined,
  });
  const rows = useMemo(() => {
    const all = moments(query.data?.pages.flatMap((page) => page.items) ?? []);
    return show === 'changes' ? all.filter((row) => !row.read) : all;
  }, [query.data, show]);
  // Looking at data is logged too and can fill whole pages; read on until
  // there is something to show.
  const pages = query.data?.pages.length ?? 0;
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = query;
  useEffect(() => {
    if (rows.length < WANTED && hasNextPage && !isFetchingNextPage && pages < MAX_AUTO_PAGES)
      void fetchNextPage();
  }, [rows.length, hasNextPage, isFetchingNextPage, fetchNextPage, pages]);

  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  if (rows.length === 0 && query.isFetchingNextPage) return <Loading />;
  if (rows.length === 0 && !query.hasNextPage) return <EmptyNotice text="Nog niets gebeurd" />;
  if (rows.length === 0)
    // Only looking at data in everything read so far; older changes may follow.
    return (
      <Stack gap="related">
        <Quiet>Geen wijzigingen in de laatste {pages * PAGE_SIZE} gebeurtenissen.</Quiet>
        <nldd-container layout="row">
          <Button text="Zoek verder terug" onClick={() => void query.fetchNextPage()} />
        </nldd-container>
      </Stack>
    );
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
            <nldd-cell hide-below="md">
              <MomentLines row={row} />
            </nldd-cell>
            {/* Narrow: when and who read above the one column. */}
            <nldd-cell hide-above="sm">
              <nldd-container gap="4">
                <nldd-text size="sm" color="secondary">
                  {`${formatMoment(row.occurred_at)} · ${row.actor}`}
                </nldd-text>
                <MomentLines row={row} />
              </nldd-container>
            </nldd-cell>
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
      <HistoryList filters={filters} label="Geschiedenis" show="changes" />
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
  { value: ALL, label: 'Alle periodes' },
  { value: '1', label: 'Vandaag', days: 1 },
  { value: '7', label: 'Afgelopen week', days: 7 },
  { value: '30', label: 'Afgelopen maand', days: 30 },
  { value: '365', label: 'Afgelopen jaar', days: 365 },
];

const SHOW_OPTIONS = [
  { value: 'changes', label: 'Wijzigingen' },
  { value: 'reads', label: 'Inzage van gegevens' },
  { value: 'all', label: 'Wijzigingen en inzage' },
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
  const [show, setShow] = useState<'changes' | 'reads' | 'all'>('changes');
  const kinds = useQuery({ queryKey: HISTORY_KEYS.kinds, queryFn: fetchKinds, enabled: isAdmin });

  const filters = useMemo<EventFilters>(() => {
    const days = PERIODS.find((option) => option.value === period)?.days;
    return {
      ...(kind !== ALL ? { subject_kind: kind } : {}),
      ...(days ? { since: startOf(days) } : {}),
      ...(show === 'reads' ? { type: 'data.read' } : {}),
    };
  }, [kind, period, show]);

  const kindOptions = useMemo(
    () => [
      { value: ALL, label: 'Alle soorten' },
      ...(kinds.data ?? [])
        .filter((value) => KIND_LABELS[value])
        .map((value) => ({ value, label: KIND_LABELS[value]! }))
        .sort((a, b) => a.label.localeCompare(b.label, 'nl')),
    ],
    [kinds.data],
  );

  return (
    <Page
      title="Activiteit"
      instanceName={instance?.name}
      back={{ href: PATHS.admin, text: 'Terug naar Beheer' }}
    >
      {isAdmin ? (
        <>
          <ActionBar
            label="Activiteit filteren"
            filters={[
              {
                label: 'Toon',
                value: show,
                onChange: (value) => setShow(value as typeof show),
                options: SHOW_OPTIONS,
                width: '200px',
              },
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
          <HistoryList
            filters={filters}
            label="Activiteit"
            show={show === 'changes' ? 'changes' : 'all'}
          />
        </>
      ) : (
        <EmptyNotice text="Activiteit is voor beheerders" />
      )}
    </Page>
  );
}
