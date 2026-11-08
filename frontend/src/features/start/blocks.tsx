/**
 * The blocks of Start, one per kind of reader. Each takes what the server
 * said and shows it; nothing is counted or summed here.
 */
import { assignmentPath } from '@/features/assignments/paths';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatEuro, formatFte, formatMonth, formatPercent } from '@/lib/format';
import { PATHS } from '@/paths';
import { IconCell } from '@/ui/Icon';
import { LinkRows, type LinkRow } from '@/ui/LinkRows';
import { Quiet, Section } from '@/ui/layout';
import type { StartData } from './api';

type Block<K extends keyof StartData> = NonNullable<StartData[K]>;

const many = (count: number, one: string, other: string) => (count === 1 ? one : other);

/** "Alle 50" under a block that shows fewer rows than there are. */
function allRow(total: number, shown: number, href: string): LinkRow[] {
  return total > shown ? [{ key: 'all', text: `Alle ${total}`, href }] : [];
}

export function ToDoBlock({ to_do }: { to_do: StartData['to_do'] }) {
  const all: LinkRow = {
    key: 'all',
    text: to_do.total > 0 ? `Alle taken (${to_do.total})` : 'Alle taken',
    href: PATHS.tasks,
  };
  const rows: LinkRow[] = to_do.groups.map((group) => ({
    key: group.task_id,
    text: group.headline,
    notice: [group.case_label, group.more_text].filter(Boolean).join(', '),
    ...(group.href ? { href: group.href } : {}),
    ...(group.overdue ? { tag: { text: 'Te laat', color: 'critical' as const } } : {}),
  }));
  return (
    <Section title="Te doen">
      {rows.length === 0 && <Quiet>Niets te doen</Quiet>}
      <LinkRows label="Te doen" rows={[...rows, all]} />
    </Section>
  );
}

export function MyWorkBlock({ block }: { block: Block<'my_work'> }) {
  return (
    <Section title="Je werkt aan">
      <RouterLinks>
        <nldd-list accessible-label="Je werkt aan">
          {block.rows.flatMap((row) => [
            <nldd-list-item key={row.assignment_id} href={assignmentPath(row.assignment_id)}>
              <nldd-text-cell text={row.name} supporting-text={row.line} />
              <IconCell concept="open" />
            </nldd-list-item>,
            ...(row.warning
              ? [
                  <nldd-list-item key={`${row.assignment_id}-warning`}>
                    <IconCell concept="attention" color="warning" />
                    <nldd-text-cell text={row.warning} />
                  </nldd-list-item>,
                ]
              : []),
          ])}
          {block.total > block.rows.length && (
            <nldd-list-item href={PATHS.assignments}>
              <nldd-text-cell text={`Alle ${block.total}`} />
              <IconCell concept="open" />
            </nldd-list-item>
          )}
          <nldd-list-item href={PATHS.person.replace(':personId', block.person_id)}>
            <nldd-text-cell text="Mijn gegevens" />
            <IconCell concept="open" />
          </nldd-list-item>
        </nldd-list>
      </RouterLinks>
    </Section>
  );
}

const VERDICT = {
  room: { text: 'Ruimte', color: 'success' },
  overrun: { text: 'Overschrijding', color: 'critical' },
} as const;

export function MyAssignmentsBlock({ block }: { block: Block<'my_assignments'> }) {
  // What asks attention first; the rest keeps the order the server gave.
  const ordered = [...block.rows].sort(
    (a, b) => Number(b.verdict === 'overrun') - Number(a.verdict === 'overrun'),
  );
  const rows: LinkRow[] = ordered.map((row) => ({
    key: row.assignment_id,
    text: row.name,
    notice: row.line,
    href: assignmentPath(row.assignment_id),
    ...(row.verdict ? { tag: VERDICT[row.verdict] } : {}),
  }));
  return (
    <Section title="Mijn opdrachten">
      <LinkRows
        label="Mijn opdrachten"
        rows={[...rows, ...allRow(block.total, block.rows.length, PATHS.assignments)]}
      />
    </Section>
  );
}

export function PlanningBlock({ block }: { block: Block<'planning'> }) {
  const rows: LinkRow[] = [];
  if (block.open_roles > 0) {
    rows.push({
      key: 'roles',
      text: `${block.open_roles} ${many(block.open_roles, 'open rol', 'open rollen')}, ${formatFte(block.open_fte)} FTE`,
      notice: 'Op het bord',
      href: PATHS.peopleBoard,
    });
  }
  if (block.idle_people > 0) {
    const from = block.idle_from ? ` vanaf ${formatMonth(block.idle_from)}` : '';
    rows.push({
      key: 'idle',
      text: `${block.idle_people} ${many(block.idle_people, 'mens', 'mensen')} zonder inzet${from}`,
      notice: 'Op het bord',
      href: PATHS.peopleBoard,
    });
  }
  if (rows.length === 0) return null;
  return (
    <Section title="Planning">
      <LinkRows label="Planning" rows={rows} />
    </Section>
  );
}

export function MyPeopleBlock({ block }: { block: Block<'my_people'> }) {
  const rows: LinkRow[] = block.rows.map((row) => {
    const notice = [
      row.now_pct !== null ? `Inzet nu ${formatPercent(row.now_pct)}` : '',
      row.free_from ? `vrij vanaf ${formatMonth(row.free_from)}` : '',
    ]
      .filter(Boolean)
      .join(', ');
    return {
      key: row.person_id,
      text: row.name,
      href: PATHS.person.replace(':personId', row.person_id),
      ...(notice ? { notice } : {}),
    };
  });
  return (
    <Section title="Mijn mensen">
      <LinkRows
        label="Mijn mensen"
        rows={[...rows, ...allRow(block.total, block.rows.length, PATHS.people)]}
      />
    </Section>
  );
}

export function FiguresBlock({ block }: { block: Block<'figures'> }) {
  const rows: LinkRow[] = [
    {
      key: 'expected',
      text: `Verwacht totaal ${block.year}`,
      notice: `Van ${formatEuro(block.budgeted_cents)} begroot`,
      end: formatEuro(block.expected_cents),
      href: PATHS.moneyTurnover,
    },
  ];
  if (block.room_cents !== undefined) {
    rows.push({
      key: 'room',
      text: `Investeerruimte ${block.year}`,
      notice: 'Na targets en kosten',
      end: block.shortfall
        ? `${formatEuro(Math.abs(block.room_cents))} tekort`
        : formatEuro(block.room_cents),
      href: PATHS.moneyInvestment,
    });
  }
  if (block.quotes_waiting > 0) {
    rows.push({
      key: 'potential',
      text: 'Potentieel',
      notice: `${block.quotes_waiting} ${many(block.quotes_waiting, 'offerte wacht', 'offertes wachten')} op akkoord, hele looptijd`,
      end: formatEuro(block.potential_cents),
      href: PATHS.moneyPotential,
    });
  }
  return (
    <Section title="Hoe staan we ervoor">
      <LinkRows label="Hoe staan we ervoor" rows={rows} />
    </Section>
  );
}

export function MyRequestsBlock({ block }: { block: Block<'my_requests'> }) {
  const rows: LinkRow[] = block.rows.map((row) => ({
    key: row.assignment_id,
    text: row.name,
    notice: row.line,
    href: PATHS.clientAssignment.replace(':assignmentId', row.assignment_id),
  }));
  return (
    <Section title="Mijn aanvragen">
      <LinkRows
        label="Mijn aanvragen"
        rows={[...rows, ...allRow(block.total, block.rows.length, PATHS.client)]}
      />
    </Section>
  );
}

export function ConnectionsBlock({ block }: { block: Block<'connections'> }) {
  if (block.problems === 0) return null;
  return (
    <Section title="Verbindingen">
      <LinkRows
        label="Verbindingen"
        rows={[
          {
            key: 'problems',
            text: `${block.problems} ${many(block.problems, 'bericht komt', 'berichten komen')} niet aan bij een andere instantie`,
            href: PATHS.peers,
          },
        ]}
      />
    </Section>
  );
}
