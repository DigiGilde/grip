import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useSearchParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatDate } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import {
  CardGrid,
  EmptyNotice,
  ErrorNotice,
  Loading,
  Page,
  Quiet,
  Section,
  SectionHeading,
  Stack,
} from '@/ui/layout';
import { TASK_KEYS, fetchBoard, fetchMyTasks, type Task } from './api';
import { ALL, BOARD_COLUMNS, MINE, filterTasks, optionsOf } from './groups';
import { TASK_PARAM, useOpenTask } from './moves';
import { RowMenu } from '@/ui/RowActions';
import { useTaskActions } from './actions';
import { TaskSheet, TaskTable } from './parts';
import { aboutLine, headlineOf, myWork } from './telling';

const VIEW_PARAM = 'weergave';
type View = 'mine' | 'board';
const VIEWS = [
  { value: 'mine', label: 'Mijn taken' },
  { value: 'board', label: 'Bord' },
] as const;

/**
 * My work in two groups: what I must do now, and what I wait for. The second
 * holds my own tasks that wait on someone, and the tasks of others on the
 * assignments I own and the vacancies I requested.
 */
function MyTasks({ onOpen }: { onOpen: (id: string) => void }) {
  const query = useQuery({ queryKey: TASK_KEYS.mine, queryFn: fetchMyTasks });
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  const { toDo, waiting } = myWork(query.data.items, query.data.awaited);
  if (toDo.length === 0 && waiting.length === 0) return <EmptyNotice text="Niets te doen" />;
  return (
    <Stack gap="section">
      <Section title="Te doen">
        {toDo.length > 0 ? (
          <TaskTable label="Te doen" tasks={toDo} onOpen={onOpen} />
        ) : (
          <Quiet>Niets te doen</Quiet>
        )}
      </Section>
      {waiting.length > 0 && (
        <Section title="Wacht op anderen">
          <TaskTable label="Wacht op anderen" tasks={waiting} onOpen={onOpen} />
        </Section>
      )}
    </Stack>
  );
}

function BoardCard({ task, onOpen }: { task: Task; onOpen: (id: string) => void }) {
  const { pathname, search } = useLocation();
  const actionsOf = useTaskActions(onOpen);
  // The board shows everyone's work, so a task is named by what must happen.
  const name = task.doer_title || headlineOf(task);
  // The name is a link that opens the task and keeps the filters.
  const params = new URLSearchParams(search);
  params.set(TASK_PARAM, task.id);
  const href = `${pathname}?${params.toString()}`;
  const due = formatDate(task.due_on);
  const who = [
    task.is_mine ? 'Voor jou' : `Voor ${task.assignee_label}`,
    task.status === 'waiting' && task.waits_on ? `wacht op ${task.waits_on}` : null,
  ]
    .filter(Boolean)
    .join(', ');
  return (
    <nldd-card>
      <nldd-container gap="8">
        <nldd-container layout="row" gap="8">
          <nldd-link href={href} text={name} />
          <nldd-spacer />
          <RowMenu name={name} actions={actionsOf(task)} />
        </nldd-container>
        <Quiet>{aboutLine(task)}</Quiet>
        <Quiet>{[who, due && `vóór ${due}`].filter(Boolean).join(' · ')}</Quiet>
        {task.overdue && <nldd-badge color="critical" text="Te laat" />}
      </nldd-container>
    </nldd-card>
  );
}

/** Every task the reader may see, as columns. Moving a card is in its menu. */
function Board({ onOpen }: { onOpen: (id: string) => void }) {
  const [params, setParams] = useSearchParams();
  const query = useQuery({ queryKey: TASK_KEYS.board, queryFn: fetchBoard });
  const filter = {
    caseLabel: params.get('zaak') ?? ALL,
    track: params.get('spoor') ?? ALL,
    assignee: params.get('wie') ?? ALL,
  };
  const set = (key: string) => (value: string) => {
    const next = new URLSearchParams(params);
    if (value === ALL) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };
  const all = query.data?.items ?? [];
  const shown = filterTasks(all, filter);
  const people = optionsOf(all, (task) => task.assignee_label, 'Iedereen');
  return (
    <Stack gap="group">
      <ActionBar
        label="Taken filteren"
        filters={[
          {
            label: 'Opdracht of vacature',
            value: filter.caseLabel,
            onChange: set('zaak'),
            options: optionsOf(all, (task) => task.case_label, 'Alle opdrachten en vacatures'),
            width: '280px',
          },
          {
            label: 'Voor wie',
            value: filter.assignee,
            onChange: set('wie'),
            options: [people[0]!, { value: MINE, label: 'Voor mij' }, ...people.slice(1)],
            width: '240px',
          },
          {
            label: 'Spoor',
            value: filter.track,
            onChange: set('spoor'),
            options: optionsOf(all, (task) => task.track_label, 'Alle sporen'),
            width: '180px',
          },
        ]}
        actions={[]}
      />
      {query.isPending && <Loading />}
      {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
      {query.data && (
        <CardGrid itemWidth="260px">
          {BOARD_COLUMNS.map((column) => {
            const tasks = shown.filter((task) => task.status === column.status);
            return (
              <Stack key={column.status} gap="related">
                <SectionHeading text={`${column.title} (${tasks.length})`} />
                <Stack gap="close">
                  {tasks.map((task) => (
                    <BoardCard key={task.id} task={task} onOpen={onOpen} />
                  ))}
                </Stack>
              </Stack>
            );
          })}
        </CardGrid>
      )}
    </Stack>
  );
}

/** What is there to do: my own tasks, or everything on a board. */
export function TasksPage() {
  const instance = useInstance();
  const containerRef = useRef<HTMLDivElement>(null);
  useRouterLinks(containerRef);
  const [params, setParams] = useSearchParams();
  const [openId, openTask] = useOpenTask();
  const view: View = params.get(VIEW_PARAM) === 'bord' ? 'board' : 'mine';
  const setView = (value: string) => {
    const next = new URLSearchParams();
    if (value === 'board') next.set(VIEW_PARAM, 'bord');
    setParams(next);
  };

  return (
    <div ref={containerRef}>
      <Page title="Taken" instanceName={instance?.name}>
        <ActionBar
          label="Weergave van de taken"
          filters={[
            { label: 'Weergave', value: view, onChange: setView, options: VIEWS, width: '180px' },
          ]}
          actions={[]}
        />
        {view === 'mine' ? <MyTasks onOpen={openTask} /> : <Board onOpen={openTask} />}
      </Page>
      <TaskSheet taskId={openId} onClose={() => openTask(null)} />
    </div>
  );
}
