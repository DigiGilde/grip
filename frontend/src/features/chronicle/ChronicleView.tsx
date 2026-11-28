import { useEffect, useRef, type RefObject } from 'react';
import { orUndef } from '@/components/nldd/events';
import { STATUS_COLORS } from '@/features/assignments/labels';
import { assignmentPartPath } from '@/features/assignments/paths';
import { formatMoment } from '@/features/history/words';
import { RouterLinks } from '@/layout/RouterLinks';
import { IconCell } from '@/ui/Icon';
import { LoadError, Loading, NameLine, Quiet, Section, SectionHeading, Stack } from '@/ui/layout';
import { CourseLine, CourseNow } from '@/ui/Workflow';
import { MOMENT_PARAM, useStand, type Moment, type Stand } from './api';
import { StandAssignmentPart } from './StandAssignmentPart';
import { StandBudgetPart } from './StandBudgetPart';
import { StandQuotesPart } from './StandQuotesPart';
import { laterKnownText, momentByline, momentText, restatedText, standTitle } from './words';

// The step cells are registered with the elements of an assignment. Tests leave
// the nldd-* elements unregistered on purpose.
if (import.meta.env.MODE !== 'test') void import('@/features/assignments/register');

const DECISION = 'Besluit';

// Focus lands here from script, not as a tab stop: no ring, as on the page heading.
const FOCUS_TARGET = { outline: 'none' };

function momentHref(assignmentId: string, seq: number): string {
  return `${assignmentPartPath(assignmentId, 'history')}?${MOMENT_PARAM}=${seq}`;
}

type Place = 'first' | 'between' | 'last' | 'only';

function placeOf(index: number, count: number): Place {
  if (count === 1) return 'only';
  if (index === 0) return 'first';
  return index === count - 1 ? 'last' : 'between';
}

function statusOf(seq: number, current: number | null): 'past' | 'current' | 'future' {
  if (current === null || seq < current) return 'past';
  return seq === current ? 'current' : 'future';
}

/** The moments, oldest first, the one being looked at marked. */
function MomentList({
  assignmentId,
  moments,
  seq,
}: {
  assignmentId: string;
  moments: readonly Moment[];
  seq: number | null;
}) {
  return (
    <nldd-list type="navigation" accessible-label="Momenten van deze opdracht">
      {moments.map((moment, index) => (
        <nldd-list-item
          key={moment.seq}
          href={momentHref(assignmentId, moment.seq)}
          current={orUndef(moment.seq === seq)}
        >
          <nldd-step-cell
            status={statusOf(moment.seq, seq)}
            position={placeOf(index, moments.length)}
          />
          <nldd-spacer-cell size="12" />
          <nldd-text-cell text={momentText(moment)} supporting-text={momentByline(moment)} />
          {moment.decision && (
            <nldd-cell width="fit-content">
              <nldd-badge color="neutral" text={DECISION} />
            </nldd-cell>
          )}
          <nldd-spacer-cell size="8" />
          <IconCell concept="open" />
        </nldd-list-item>
      ))}
    </nldd-list>
  );
}

/** Where the assignment stood: the course, and how it ended if it had. */
function StandCourse({ stand }: { stand: Stand }) {
  const { course, assignment, moment } = stand;
  const ended = course ? course.ended : stand.incomplete ? null : assignment.status_label;
  return (
    <Stack gap="related">
      {course && <CourseNow course={course} />}
      {course && !course.ended && (
        <CourseLine
          course={course}
          accessibleLabel={`Verloop op ${formatMoment(moment.occurred_at)}`}
        />
      )}
      {ended && (
        <nldd-container layout="row">
          <nldd-badge color={STATUS_COLORS[assignment.status] ?? 'neutral'} text={ended} />
        </nldd-container>
      )}
      {/* The sentence names the role; the name is a fact of the stand. */}
      {course?.next && assignment.owner_name && <Quiet>Eigenaar: {assignment.owner_name}</Quiet>}
    </Stack>
  );
}

function BackToNow({ assignmentId }: { assignmentId: string }) {
  return (
    <nldd-link href={assignmentPartPath(assignmentId, 'history')} text="Terug naar nu" size="md" />
  );
}

/** How things stood at one moment. */
function StandAtMoment({
  assignmentId,
  seq,
  seenRef,
}: {
  assignmentId: string;
  seq: number;
  /** The moment focus last went to, kept above this part: it outlives the list without a moment. */
  seenRef: RefObject<number | null>;
}) {
  const query = useStand(assignmentId, seq);
  const heading = useRef<HTMLDivElement>(null);
  const arrived = query.isPlaceholderData ? undefined : query.data?.moment.seq;
  // Another moment: focus goes to the line that says which one this is. In a
  // frame, because the containers around it have no box yet when they are new;
  // never cancelled, because StrictMode reruns this effect on mount.
  useEffect(() => {
    if (arrived === undefined || seenRef.current === arrived) return;
    requestAnimationFrame(() => {
      seenRef.current = arrived;
      heading.current?.focus();
    });
  }, [arrived, seenRef]);

  if (query.isPending) return <Loading />;
  if (query.isError) {
    return (
      <Stack gap="related">
        <LoadError error={query.error} retry={() => void query.refetch()} what="Dit moment" />
        <BackToNow assignmentId={assignmentId} />
      </Stack>
    );
  }
  const stand = query.data;
  const { moment } = stand;
  return (
    <Stack gap="group">
      <Stack gap="close">
        <div ref={heading} tabIndex={-1} style={FOCUS_TARGET}>
          <SectionHeading text={standTitle(moment.occurred_at)} />
        </div>
        <NameLine
          badges={moment.decision ? <nldd-badge color="neutral" text={DECISION} /> : undefined}
        >
          <nldd-text>
            <p>{momentText(moment)}</p>
          </nldd-text>
        </NameLine>
        {(moment.lines ?? []).map((line) => (
          <Quiet key={line}>{line}</Quiet>
        ))}
        {stand.incomplete && <Quiet>Een deel van de waarden is gewist.</Quiet>}
        {(stand.outside_values ?? stand.outside).map((line) => (
          <Quiet key={line}>{line}</Quiet>
        ))}
        {stand.later_known.map((later) => (
          <nldd-link
            key={later.seq}
            href={momentHref(assignmentId, later.seq)}
            text={laterKnownText(later)}
            size="sm"
          />
        ))}
        {stand.restated.map((entry) => (
          <nldd-link
            key={entry.seq}
            href={momentHref(assignmentId, entry.seq)}
            text={restatedText(entry)}
            size="sm"
          />
        ))}
      </Stack>
      <StandCourse stand={stand} />
      <StandAssignmentPart stand={stand} />
      {stand.budget && <StandBudgetPart budget={stand.budget} />}
      <StandQuotesPart quotes={stand.quotes} />
      <nldd-container layout="wrap" gap="16" vertical-alignment="center">
        {stand.previous_seq !== null && (
          <nldd-link href={momentHref(assignmentId, stand.previous_seq)} text="Vorige" size="md" />
        )}
        {stand.next_seq !== null && (
          <nldd-link href={momentHref(assignmentId, stand.next_seq)} text="Volgende" size="md" />
        )}
        <BackToNow assignmentId={assignmentId} />
      </nldd-container>
    </Stack>
  );
}

interface ChronicleViewProps {
  assignmentId: string;
  moments: readonly Moment[];
  /** The moment in the address. */
  seq: number | null;
}

/** Walking through the moments of an assignment, and how things stood at each one. */
export function ChronicleView({ assignmentId, moments, seq }: ChronicleViewProps) {
  // A first load of an address with a moment leaves focus where the page starts.
  const seenRef = useRef(seq);
  const listTarget = useRef<HTMLDivElement>(null);
  // Back to now: focus goes to the list, in a frame as for a moment.
  useEffect(() => {
    if (seq !== null || seenRef.current === null) return;
    requestAnimationFrame(() => {
      seenRef.current = null;
      listTarget.current?.focus();
    });
  }, [seq]);
  const list = <MomentList assignmentId={assignmentId} moments={moments} seq={seq} />;
  return (
    <RouterLinks>
      {seq === null ? (
        <div ref={listTarget} tabIndex={-1} style={FOCUS_TARGET}>
          {list}
        </div>
      ) : (
        <Stack gap="section">
          <StandAtMoment assignmentId={assignmentId} seq={seq} seenRef={seenRef} />
          {moments.length > 0 && <Section title="Momenten">{list}</Section>}
        </Stack>
      )}
    </RouterLinks>
  );
}
