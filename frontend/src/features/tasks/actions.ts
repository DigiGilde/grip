/** What a reader can do with a task from a menu: read it, go to its work, move it. */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { RowAction } from '@/ui/RowActions';
import { TASK_KEYS, setTaskStatus, type Task, type TaskStatus } from './api';
import { movesOf } from './moves';
import { goesToWork, workHref } from './telling';

function useMoveTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status, version }: { id: string; status: TaskStatus; version?: number }) =>
      setTaskStatus(id, status, version),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASK_KEYS.all }),
  });
}

/** What else a task can do besides its one action: be read, and be moved. */
export function useTaskActions(onOpen: (id: string) => void): (task: Task) => RowAction[] {
  const move = useMoveTask();
  return (task) => {
    const href = workHref(task);
    return [
      { text: 'Bekijk de taak', onSelect: () => onOpen(task.id) },
      // The way to the work for who looks on; who must do it gets there by the name.
      ...(href && !goesToWork(task) ? [{ text: 'Ga naar de plek van het werk', href }] : []),
      ...movesOf(task).map((item) => ({
        text: item.text,
        onSelect: () => move.mutate({ id: task.id, status: item.status, version: task.version }),
      })),
    ];
  };
}
