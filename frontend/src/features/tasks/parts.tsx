/**
 * The parts every task screen shares: the menu of what a task can do, the
 * table of tasks, and the sheet with one task.
 */
import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { useNlddEvent } from '@/components/nldd/events';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate } from '@/lib/format';
import { Facts, FormSheet, Quiet, Stack, type Fact } from '@/ui/layout';
import { OpenCell, OpenRow, ROW_ACTIONS_COLUMN } from '@/ui/RowActions';
import { TextInput } from '@/features/vacancies/ui';
import {
  TASK_KEYS,
  addTaskNote,
  fetchTask,
  setTaskStatus,
  type Task,
  type TaskStatus,
} from './api';
import { STATUS_COLORS, closesBecause, whoLine } from './groups';
import { movesOf } from './moves';

if (import.meta.env.MODE !== 'test') void import('./register');

function useMoveTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: TaskStatus }) => setTaskStatus(id, status),
    onSettled: () => queryClient.invalidateQueries({ queryKey: TASK_KEYS.all }),
  });
}

function MoveItem({ text, onChoose }: { text: string; onChoose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', onChoose);
  return <nldd-menu-item ref={ref} text={text} />;
}

/**
 * One quiet button with what a task can do: move it between the columns, or
 * go to where the work is. Reached with Tab and worked with the arrow keys,
 * so nothing on the board needs dragging.
 */
export function TaskMenu({ task }: { task: Task }) {
  const move = useMoveTask();
  const moves = movesOf(task);
  if (moves.length === 0 && !task.link) return null;
  return (
    <nldd-icon-button
      icon="more"
      size="sm"
      appearance="neutral-transparent"
      popup-type="menu"
      accessible-label={`Meer acties voor ${task.title}`}
      text={`Meer acties voor ${task.title}`}
    >
      <nldd-menu slot="popup" placement="bottom-end">
        {moves.map((item) => (
          <MoveItem
            key={item.status}
            text={item.text}
            onChoose={() => move.mutate({ id: task.id, status: item.status })}
          />
        ))}
        {task.link && <nldd-menu-item text="Ga naar het werk" href={task.link} />}
      </nldd-menu>
    </nldd-icon-button>
  );
}

export function StatusBadge({ task }: { task: Task }) {
  return <nldd-badge color={STATUS_COLORS[task.status]} text={task.status_label} />;
}

interface TaskTableProps {
  label: string;
  tasks: readonly Task[];
  /** Leave the case out on the page of the case itself. */
  withCase?: boolean;
  onOpen: (id: string) => void;
}

/**
 * Tasks as a table: what to do, for whom, by when and how it stands. The
 * row opens the task; the menu at the end moves it.
 */
export function TaskTable({ label, tasks, withCase = true, onOpen }: TaskTableProps) {
  const columns = `minmax(260px,2fr) minmax(180px,1fr) 130px 170px ${ROW_ACTIONS_COLUMN}`;
  const narrow = `minmax(180px,1fr) 110px ${ROW_ACTIONS_COLUMN}`;
  return (
    <nldd-table accessible-label={label} columns={columns} sm-columns={narrow}>
      <nldd-table-row slot="header">
        <nldd-text-cell text="Taak" />
        <nldd-text-cell text="Voor wie" hide-below="md" />
        <nldd-text-cell text="Vóór" />
        <nldd-text-cell text="Status" hide-below="md" />
        <nldd-cell />
      </nldd-table-row>
      {tasks.map((task) => (
        <OpenRow key={task.id} onOpen={() => onOpen(task.id)}>
          <OpenCell
            text={task.title}
            supportingText={withCase ? `${task.case_label} · ${task.track_label}` : undefined}
            accessibleLabel={`Open ${task.title}`}
            onOpen={() => onOpen(task.id)}
          />
          <nldd-text-cell hide-below="md" text={whoLine(task)} />
          <nldd-text-cell
            text={formatDate(task.due_on)}
            {...(task.overdue ? { color: 'critical', 'supporting-text': 'Te laat' } : {})}
          />
          <nldd-cell hide-below="md">
            <StatusBadge task={task} />
          </nldd-cell>
          <nldd-cell>
            <TaskMenu task={task} />
          </nldd-cell>
        </OpenRow>
      ))}
    </nldd-table>
  );
}

function taskFacts(task: Task): Fact[] {
  const closed = task.completed_at
    ? task.completed_by_fact
      ? `${formatDate(task.completed_at)}, vanzelf`
      : `${formatDate(task.completed_at)}${task.completed_by_name ? `, door ${task.completed_by_name}` : ''}`
    : undefined;
  return [
    { label: 'Hoort bij', value: `${task.case_label} · ${task.track_label}` },
    { label: 'Voor wie', value: task.assignee_label },
    { label: 'Wacht op', value: task.status === 'waiting' ? (task.waiting_on ?? undefined) : undefined },
    { label: 'Vóór', value: formatDate(task.due_on) || undefined },
    { label: 'Status', value: task.status_label },
    { label: 'Afgerond', value: closed },
  ].filter((fact) => fact.value !== undefined);
}

/**
 * One task: its facts, why it closes, and the notes. The one action is
 * adding a note; moving the task is in its menu.
 */
export function TaskSheet({ taskId, onClose }: { taskId: string | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  // The sheet keeps its last task while it slides out.
  const [lastId, setLastId] = useState<string | null>(null);
  if (taskId && taskId !== lastId) {
    setLastId(taskId);
    setNote('');
    setError(null);
  }
  const shownId = taskId ?? lastId;
  const query = useQuery({
    queryKey: TASK_KEYS.detail(shownId ?? ''),
    queryFn: () => fetchTask(shownId ?? ''),
    enabled: shownId !== null,
  });
  const save = useMutation({
    mutationFn: () => addTaskNote(shownId ?? '', note.trim()),
    onSuccess: () => {
      setNote('');
      setError(null);
      void queryClient.invalidateQueries({ queryKey: TASK_KEYS.all });
    },
    onError: (failure) => setError(errorMessage(failure)),
  });
  const task = query.data;
  const because = task ? closesBecause(task) : null;
  const notes = task?.notes ?? [];

  return (
    <FormSheet
      open={taskId !== null}
      title={task?.title ?? 'Taak'}
      submitText="Bewaar notitie"
      onSubmit={() => {
        if (note.trim() === '') setError('Schrijf eerst een notitie.');
        else save.mutate();
      }}
      onClose={onClose}
      busy={save.isPending}
      error={error ?? (query.isError ? errorMessage(query.error) : null)}
    >
      {task && (
        <Stack gap="group">
          <Facts label={`Gegevens van ${task.title}`} facts={taskFacts(task)} labelWidth="120px" />
          {because && <Quiet>{because}</Quiet>}
          {task.link && (
            <RouterLinks>
              <nldd-link href={task.link} text="Ga naar het werk" size="md" />
            </RouterLinks>
          )}
          {notes.length > 0 && (
            <Stack gap="related">
              {notes.map((item) => (
                <Stack key={item.id} gap="tight">
                  <nldd-text>{item.body}</nldd-text>
                  <Quiet>
                    {[item.author_name, formatDate(item.created_at)].filter(Boolean).join(' · ')}
                  </Quiet>
                </Stack>
              ))}
            </Stack>
          )}
        </Stack>
      )}
      <TextInput label="Notitie" value={note} onChange={setNote} multiline />
    </FormSheet>
  );
}
