/** How tasks are ordered and grouped on the screens. Pure, so it is tested. */
import type { Task, TaskStatus } from './api';

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
        (filter.assignee === MINE
          ? task.is_mine === true
          : task.assignee_label === filter.assignee)),
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
