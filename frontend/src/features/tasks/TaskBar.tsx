import { useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useNlddEvent } from '@/components/nldd/events';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PATHS } from '@/paths';
import { TASK_KEYS, fetchTask } from './api';
import { FOR_TASK_PARAM, dueWords, headlineOf, withoutTask } from './telling';

if (import.meta.env.MODE !== 'test') void import('./register');

/** While the bar is shown it looks again this often, so it sees the work being done. */
const LOOK_AGAIN_MS = 4000;

/**
 * The task a reader came to this page to do, as one calm bar above the page.
 *
 * A task in a list leads to the place where its work is done, with the task
 * named in the address. This bar reads that name and says what to do here,
 * and says so again when the work is done and the task has closed. Without a
 * task in the address it draws nothing.
 */
export function TaskBar() {
  const [params] = useSearchParams();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const ref = useRef<HTMLElement>(null);
  const linksRef = useRef<HTMLDivElement>(null);
  useRouterLinks(linksRef);
  const taskId = params.get(FOR_TASK_PARAM);
  const query = useQuery({
    queryKey: TASK_KEYS.detail(taskId ?? ''),
    queryFn: async () => {
      const task = await fetchTask(taskId ?? '');
      // The badge in the navigation follows as soon as the task closes.
      if (task.status === 'done') void queryClient.invalidateQueries({ queryKey: TASK_KEYS.count });
      return task;
    },
    enabled: taskId !== null,
    retry: false,
    refetchInterval: (latest) => (latest.state.data?.status === 'done' ? false : LOOK_AGAIN_MS),
  });
  useNlddEvent(ref, 'dismiss', () =>
    navigate(`${pathname}${withoutTask(search)}`, { replace: true }),
  );
  const task = query.data;
  if (!taskId || !task) return null;
  const done = task.status === 'done';
  const gone = task.status === 'obsolete';
  const name = headlineOf(task);
  const words = done ? `Gedaan: ${name}` : gone ? `Niet meer nodig: ${name}` : `Taak: ${name}`;
  const detail =
    done || gone
      ? undefined
      : [task.instruction, dueWords(task) ? `${dueWords(task)}.` : ''].filter(Boolean).join(' ');
  return (
    <div ref={linksRef}>
      <nldd-container padding="8">
        <nldd-banner
          ref={ref}
          variant={done ? 'success' : 'accent'}
          size="sm"
          text={words}
          {...(detail ? { 'supporting-text': detail } : {})}
          dismissible
        >
          <nldd-button slot="actions" size="sm" href={PATHS.tasks} text="Terug naar Taken" />
        </nldd-banner>
      </nldd-container>
    </div>
  );
}
