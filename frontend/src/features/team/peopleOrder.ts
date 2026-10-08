import type { BoardPerson } from '@/features/allocations/board/api';
import { formatMonth } from '@/lib/format';
import { monthShort } from '@/ui/timeline/layout';
import type { Person } from './api';

interface Signal {
  text: string;
  /** Lower comes first in the list. */
  rank: number;
  attention: boolean;
}

const QUIET: Signal = { text: '', rank: 3, attention: false };

/**
 * What to know about someone's work at a glance, most urgent first: planned
 * above 100 percent, work that ends, room.
 */
export function signalOf(person: Person, row: BoardPerson | undefined): Signal {
  if (!row) return QUIET;
  const over = row.over_months ?? [];
  if (over.length > 0) {
    return {
      text: `Boven 100% in ${over.map((month) => monthShort(month)).join(', ')}`,
      rank: 0,
      attention: true,
    };
  }
  if (row.idle_from) {
    const idleNow = (person.current_assignment_count ?? 0) === 0;
    return {
      text: idleNow ? 'Geen inzet gepland' : `Geen inzet vanaf ${formatMonth(row.idle_from)}`,
      rank: 1,
      attention: true,
    };
  }
  if (row.room_from) {
    return { text: `Ruimte vanaf ${formatMonth(row.room_from)}`, rank: 2, attention: false };
  }
  return QUIET;
}

/** Who needs attention first; within one kind of signal by name. */
export function orderPeople(
  people: Person[],
  rows: Map<string, BoardPerson>,
): { person: Person; signal: Signal }[] {
  return people
    .map((person) => ({ person, signal: signalOf(person, rows.get(person.id)) }))
    .sort(
      (a, b) => a.signal.rank - b.signal.rank || a.person.name.localeCompare(b.person.name, 'nl'),
    );
}
