import { useQuery } from '@tanstack/react-query';
import { RouterLinks } from '@/layout/RouterLinks';
import { PATHS } from '@/paths';
import { Quiet, Stack } from '@/ui/layout';
import { TASK_KEYS, fetchMyTasks, type Task } from './api';
import { TASK_PARAM } from './moves';
import { aboutLine, dueWords, goesToWork, headlineOf, myWork, workHref } from './telling';
import { useTellApart } from './tellApart';

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
  // Only what the reader must do now; what waits on others is on the Taken page.
  const { toDo, waiting } = myWork(query.data.items, query.data.awaited);
  const tasks = toDo.slice(0, limit);
  return <Shown tasks={tasks} toDo={toDo.length} waiting={waiting.length} />;
}

function Shown({ tasks, toDo, waiting }: { tasks: Task[]; toDo: number; waiting: number }) {
  const apartOf = useTellApart(tasks);
  if (tasks.length === 0) {
    return waiting > 0 ? (
      <RouterLinks>
        <Stack gap="close">
          <Quiet>Niets te doen</Quiet>
          <nldd-link href={PATHS.tasks} text={`Wacht op anderen (${waiting})`} size="md" />
        </Stack>
      </RouterLinks>
    ) : (
      <Quiet>Niets te doen</Quiet>
    );
  }
  return (
    <RouterLinks>
      <Stack gap="related">
        <Stack gap="close">
          {tasks.map((task) => (
            <Stack key={task.id} gap="tight">
              <nldd-link
                href={
                  (goesToWork(task) ? workHref(task) : null) ??
                  `${PATHS.tasks}?${TASK_PARAM}=${task.id}`
                }
                text={headlineOf(task)}
              />
              <Quiet>
                {[aboutLine(task), apartOf(task), dueWords(task)].filter(Boolean).join(' · ')}
              </Quiet>
            </Stack>
          ))}
        </Stack>
        <nldd-link
          href={PATHS.tasks}
          text={toDo > tasks.length ? `Alle taken (${toDo})` : 'Naar Taken'}
          size="md"
        />
      </Stack>
    </RouterLinks>
  );
}
