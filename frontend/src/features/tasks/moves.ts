/** Opening a task through the address, and the moves a reader can make with it. */
import { useSearchParams } from 'react-router-dom';
import type { Task, TaskStatus } from './api';
import { isOpen } from './groups';

/** The search parameter that holds the task whose sheet is open. */
export const TASK_PARAM = 'taak';

/** Opens and closes the sheet of one task through the address. */
export function useOpenTask(): [string | null, (id: string | null) => void] {
  const [params, setParams] = useSearchParams();
  const open = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set(TASK_PARAM, id);
    else next.delete(TASK_PARAM);
    setParams(next, { replace: id === null });
  };
  return [params.get(TASK_PARAM), open];
}

const MOVES: readonly { status: TaskStatus; text: string }[] = [
  { status: 'todo', text: 'Zet op te doen' },
  { status: 'doing', text: 'Begin' },
  { status: 'waiting', text: 'Wacht op een ander' },
  { status: 'done', text: 'Rond af' },
];

/** The moves this reader can make with this task. A fact-closed task has no "Rond af". */
export function movesOf(task: Task): { status: TaskStatus; text: string }[] {
  if (!task.can_change) return [];
  return MOVES.filter(
    (move) =>
      move.status !== task.status &&
      (move.status !== 'done' || task.can_complete === true) &&
      (isOpen(task) || move.status === 'todo'),
  );
}
