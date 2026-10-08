/** How tasks are ordered and grouped on the screens. Pure, so it is tested. */
import type { Task, TaskStatus } from './api';

export type DueGroup = 'overdue' | 'thisWeek' | 'later';

export const DUE_GROUPS: readonly { key: DueGroup; title: string }[] = [
  { key: 'overdue', title: 'Te laat' },
  { key: 'thisWeek', title: 'Deze week' },
  { key: 'later', title: 'Later' },
];

function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/** The Sunday that ends the week of `today`. */
export function endOfWeek(today: Date): string {
  const end = new Date(today);
  end.setDate(end.getDate() + ((7 - end.getDay()) % 7));
  return isoDate(end);
}

/** Too late, due before the week is out, or later. No date counts as later. */
export function dueGroup(task: Task, today: Date): DueGroup {
  if (!task.due_on) return 'later';
  if (task.overdue || task.due_on < isoDate(today)) return 'overdue';
  return task.due_on <= endOfWeek(today) ? 'thisWeek' : 'later';
}

export function byDueGroup(tasks: readonly Task[], today: Date): Record<DueGroup, Task[]> {
  const groups: Record<DueGroup, Task[]> = { overdue: [], thisWeek: [], later: [] };
  for (const task of tasks) groups[dueGroup(task, today)].push(task);
  return groups;
}

/** The columns of the board, in reading order. */
export const BOARD_COLUMNS: readonly { status: TaskStatus; title: string }[] = [
  { status: 'todo', title: 'Te doen' },
  { status: 'doing', title: 'Bezig' },
  { status: 'waiting', title: 'Wacht op een ander' },
  { status: 'done', title: 'Klaar' },
];

export const STATUS_COLORS: Record<TaskStatus, 'neutral' | 'accent' | 'success' | 'warning'> = {
  todo: 'neutral',
  doing: 'accent',
  waiting: 'warning',
  done: 'success',
  obsolete: 'neutral',
};

export const isOpen = (task: Task) => task.status !== 'done' && task.status !== 'obsolete';

export interface BoardFilter {
  caseLabel: string;
  track: string;
  assignee: string;
}

export const ALL = '';
export const MINE = 'mine';

export function filterTasks(tasks: readonly Task[], filter: BoardFilter): Task[] {
  return tasks.filter(
    (task) =>
      (filter.caseLabel === ALL || task.case_label === filter.caseLabel) &&
      (filter.track === ALL || task.track_label === filter.track) &&
      (filter.assignee === ALL ||
        (filter.assignee === MINE ? task.is_mine === true : task.assignee_label === filter.assignee)),
  );
}

/** The distinct values of one field, sorted, as options under "all". */
export function optionsOf(
  tasks: readonly Task[],
  pick: (task: Task) => string,
  allLabel: string,
): { value: string; label: string }[] {
  const values = [...new Set(tasks.map(pick))].sort((a, b) => a.localeCompare(b, 'nl'));
  return [{ value: ALL, label: allLabel }, ...values.map((value) => ({ value, label: value }))];
}

/** What stands under the title of a task: for whom, or on whom it waits. */
export function whoLine(task: Task): string {
  if (task.status === 'waiting' && task.waiting_on) return `Wacht op ${task.waiting_on}`;
  return task.assignee_label;
}

/** Why a task cannot be ticked, in the words of its fact. */
export function closesBecause(task: Task): string | null {
  if (!task.closes_by_fact || !task.closing_fact_label) return null;
  return `Sluit vanzelf zodra ${task.closing_fact_label}.`;
}
