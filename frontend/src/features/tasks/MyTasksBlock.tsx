import { useQuery } from '@tanstack/react-query';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate } from '@/lib/format';
import { PATHS } from '@/paths';
import { Quiet, Stack } from '@/ui/layout';
import { TASK_KEYS, fetchMyTasks } from './api';
import { firstByDue } from './groups';
import { TASK_PARAM } from './moves';

if (import.meta.env.MODE !== 'test') void import('./register');

interface MyTasksBlockProps {
  /** How many tasks to show at most. */
  limit?: number;
}

/**
 * My first few tasks by due date, for the start page: no board, no table,
 * and a link to the Taken page for the rest. It brings no heading of its
 * own; the page that places it names the section.
 */
export function MyTasksBlock({ limit = 5 }: MyTasksBlockProps) {
  const query = useQuery({ queryKey: TASK_KEYS.mine, queryFn: fetchMyTasks });
  if (query.isPending) return null;
  if (query.isError) return <Quiet>De taken zijn nu niet te laden.</Quiet>;
  const tasks = firstByDue(query.data.items, limit);
  if (tasks.length === 0) return <Quiet>Niets te doen</Quiet>;
  const more = query.data.items.length - tasks.length;
  return (
    <RouterLinks>
      <Stack gap="related">
        <Stack gap="close">
          {tasks.map((task) => (
            <Stack key={task.id} gap="tight">
              <nldd-link href={`${PATHS.tasks}?${TASK_PARAM}=${task.id}`} text={task.title} />
              <Quiet>
                {[
                  task.case_label,
                  task.due_on && `vóór ${formatDate(task.due_on)}`,
                  task.overdue && 'te laat',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </Quiet>
            </Stack>
          ))}
        </Stack>
        <nldd-link
          href={PATHS.tasks}
          text={more > 0 ? `Alle taken (${query.data.items.length})` : 'Naar Taken'}
          size="md"
        />
      </Stack>
    </RouterLinks>
  );
}
