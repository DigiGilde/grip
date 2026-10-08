import { useQuery } from '@tanstack/react-query';
import { fetchMyTasks, TASK_KEYS } from '@/features/tasks/api';
import { formatDate } from '@/lib/format';
import { PATHS } from '@/paths';
import { Section, Stack } from '@/ui/layout';

interface MyTasksProps {
  /** How many tasks to show before the link to the Taken page. */
  limit?: number;
}

/**
 * SLOT FOR THE TASK LAYER: the reader's own first few tasks by due date and
 * a link to the Taken page. It reads the tasks feature's own API and draws
 * nothing while there are no tasks. The tasks feature may replace this file
 * with a component of its own; the start page only passes `limit`.
 */
export function MyTasks({ limit = 4 }: MyTasksProps) {
  const query = useQuery({ queryKey: TASK_KEYS.mine, queryFn: fetchMyTasks, retry: false });
  const open = (query.data?.items ?? []).filter(
    (task) => task.status !== 'done' && task.status !== 'obsolete',
  );
  if (open.length === 0) return null;
  const first = [...open]
    .sort((a, b) => (a.due_on ?? '9999').localeCompare(b.due_on ?? '9999'))
    .slice(0, limit);
  return (
    <Section title="Mijn taken" level={3}>
      <Stack gap="close">
        {first.map((task) => (
          <nldd-container key={task.id} gap="4">
            <nldd-link href={task.link ?? `${PATHS.tasks}?taak=${task.id}`} text={task.title} />
            <nldd-text color="secondary" size="sm">
              {[
                task.case_label,
                task.due_on ? `vóór ${formatDate(task.due_on)}` : '',
                task.overdue ? 'te laat' : '',
              ]
                .filter(Boolean)
                .join(', ')}
            </nldd-text>
          </nldd-container>
        ))}
        <nldd-link
          href={PATHS.tasks}
          text={open.length > first.length ? `Alle ${open.length} taken` : 'Naar Taken'}
          size="md"
        />
      </Stack>
    </Section>
  );
}
