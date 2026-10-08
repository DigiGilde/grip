/**
 * The parts every task screen shares: the table of tasks, and the sheet that
 * tells one task.
 *
 * A task is told to its reader in this order: what to do (or who must do
 * what), on what, why it is there, by when, and the one action that does it.
 * A task that is the reader's to do is activated by its name and goes to the
 * place where the work is done; any other task opens to be read.
 */
import { useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate } from '@/lib/format';
import { Facts, Quiet, Stack, type Fact } from '@/ui/layout';
import { OpenCell, OpenRow, ROW_ACTIONS_COLUMN, RowActions } from '@/ui/RowActions';
import { Button, TextInput } from '@/features/vacancies/ui';
import { TASK_KEYS, addTaskNote, fetchTask, setTaskStatus, type Task } from './api';
import { useTaskActions } from './actions';
import { aboutLine, aboutLinks, finishesHere, goesToWork, headlineOf, workHref } from './telling';
import { useTellApart } from './tellApart';

if (import.meta.env.MODE !== 'test') void import('./register');

/** The quiet line under the name of a task in a list. */
function detailLine(task: Task, withCase: boolean, apart?: string): string | undefined {
  const parts = [
    task.needs_me !== true && task.waits_on ? `Wacht op ${task.waits_on}` : null,
    withCase ? aboutLine(task) : null,
    // Only when another task in the list reads the same: where its vacancy stands.
    withCase ? apart : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : undefined;
}

interface TaskTableProps {
  label: string;
  tasks: readonly Task[];
  /** Leave the case out on the page of the case itself. */
  withCase?: boolean;
  /** Opens a task to be read. */
  onOpen: (id: string) => void;
}

/**
 * Tasks as a table: what, on what and by when. The name of a task that is
 * the reader's to do leads to the place where it is done; the name of any
 * other task opens it. The menu at the end holds the rest.
 */
export function TaskTable({ label, tasks, withCase = true, onOpen }: TaskTableProps) {
  const navigate = useNavigate();
  const actionsOf = useTaskActions(onOpen);
  const apartOf = useTellApart(tasks);
  // A list in which nothing has a date has no column for it.
  const withDue = tasks.some((task) => task.due_on);
  const columns = `minmax(280px,1fr) ${withDue ? '180px ' : ''}${ROW_ACTIONS_COLUMN}`;
  const narrow = `minmax(180px,1fr) ${withDue ? '110px ' : ''}${ROW_ACTIONS_COLUMN}`;
  return (
    <nldd-table accessible-label={label} columns={columns} sm-columns={narrow}>
      <nldd-table-row slot="header">
        <nldd-text-cell text="Taak" />
        {withDue && <nldd-text-cell text="Vóór" />}
        <nldd-cell />
      </nldd-table-row>
      {tasks.map((task) => {
        const name = headlineOf(task);
        const href = workHref(task);
        const activate = goesToWork(task) && href ? () => navigate(href) : () => onOpen(task.id);
        return (
          <OpenRow key={task.id} onOpen={activate}>
            <OpenCell
              text={name}
              supportingText={detailLine(task, withCase, apartOf(task))}
              accessibleLabel={goesToWork(task) ? `${name}: ga naar het werk` : `Bekijk ${name}`}
              onOpen={activate}
            />
            {withDue && (
              <nldd-text-cell
                text={formatDate(task.due_on)}
                {...(task.overdue ? { color: 'critical', 'supporting-text': 'Te laat' } : {})}
              />
            )}
            <RowActions name={name} actions={actionsOf(task)} />
          </OpenRow>
        );
      })}
    </nldd-table>
  );
}

function closedWords(task: Task): string | undefined {
  if (!task.completed_at) return undefined;
  const by = task.completed_by_fact
    ? ''
    : task.completed_by_name
      ? `, door ${task.completed_by_name}`
      : '';
  return `${formatDate(task.completed_at)}${by}`;
}

function AboutLinks({ task }: { task: Task }) {
  const links = aboutLinks(task);
  if (links.length === 0) return <nldd-text>{task.case_label}</nldd-text>;
  return (
    <nldd-container gap="4">
      {links.map((link) => (
        <nldd-link key={link.href} href={link.href} text={link.text} />
      ))}
    </nldd-container>
  );
}

function taskFacts(task: Task): Fact[] {
  const due = task.due_on
    ? `${formatDate(task.due_on)}${task.overdue ? ', te laat' : ''}`
    : undefined;
  return [
    { label: 'Waarover', value: <AboutLinks task={task} /> },
    { label: 'Waarom nu', value: task.why ?? undefined },
    { label: 'Vóór', value: due },
    { label: 'Vervolg', value: task.then ?? undefined },
    { label: 'Van wie', value: task.is_mine ? undefined : task.assignee_label },
    { label: 'Afgerond', value: closedWords(task) },
  ].filter((fact) => fact.value !== undefined);
}

/** What the request still misses, as one plain sentence. */
function missingWords(task: Task): string | null {
  const missing = (task.checklist ?? []).filter((item) => !item.done).map((item) => item.text);
  if (missing.length === 0) return null;
  return `Ontbreekt nog: ${missing.join(', ').toLowerCase()}.`;
}

interface TaskSheetProps {
  taskId: string | null;
  onClose: () => void;
}

/**
 * One task, told to its reader: what to do or who must do it, on what, why
 * and by when. Its one button does the work or leads to it; who only waits
 * gets no button. A note is the quiet thing at the end.
 */
export function TaskSheet({ taskId, onClose }: TaskSheetProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const sheetRef = useRef<HTMLElement>(null);
  const barRef = useRef<HTMLElement>(null);
  const titleId = useId();
  const [note, setNote] = useState('');
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The sheet keeps its last task while it slides out.
  const [lastId, setLastId] = useState<string | null>(null);
  if (taskId && taskId !== lastId) {
    setLastId(taskId);
    setNote('');
    setWriting(false);
    setError(null);
  }
  const shownId = taskId ?? lastId;
  useNlddEvent(sheetRef, 'close', onClose);
  useNlddEvent(barRef, 'dismiss', onClose);
  const query = useQuery({
    queryKey: TASK_KEYS.detail(shownId ?? ''),
    queryFn: () => fetchTask(shownId ?? ''),
    enabled: shownId !== null,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: TASK_KEYS.all });
  const save = useMutation({
    mutationFn: () => addTaskNote(shownId ?? '', note.trim()),
    onSuccess: () => {
      setNote('');
      setWriting(false);
      setError(null);
      void refresh();
    },
    onError: (failure) => setError(errorMessage(failure)),
  });
  const finish = useMutation({
    mutationFn: () => setTaskStatus(shownId ?? '', 'done'),
    onSuccess: () => {
      void refresh();
      onClose();
    },
    onError: (failure) => setError(errorMessage(failure)),
  });
  const task = query.data;
  const title = task ? headlineOf(task) : 'Taak';
  const href = task ? workHref(task) : null;
  const notes = task?.notes ?? [];
  const problem = error ?? (query.isError ? errorMessage(query.error) : null);
  const missing = task ? missingWords(task) : null;

  return createPortal(
    <nldd-sheet ref={sheetRef} open={orUndef(taskId !== null)} placement="right" width="480px">
      <nldd-page>
        <nldd-top-title-bar
          ref={barRef}
          slot="header"
          text={title}
          dismiss-text="Sluit"
          collapse-anchor={titleId}
        />
        <nldd-simple-section>
          <nldd-title id={titleId} slot="header" size={2} text={title} heading-level={1} />
          <RouterLinks>
            <Stack gap="group">
              {problem ? <nldd-banner variant="critical" size="sm" text={problem} /> : null}
              {task && (
                <>
                  <Stack gap="related">
                    {task.instruction ? <nldd-text>{task.instruction}</nldd-text> : null}
                    {missing ? <nldd-text>{missing}</nldd-text> : null}
                    {task.blocked ? (
                      <nldd-banner variant="warning" size="sm" text={task.blocked} />
                    ) : null}
                    {finishesHere(task) ? (
                      <nldd-button-group>
                        <Button
                          text="Rond af"
                          appearance="primary"
                          loading={finish.isPending}
                          onClick={() => finish.mutate()}
                        />
                        {href ? <nldd-button href={href} text="Ga naar het werk" /> : null}
                      </nldd-button-group>
                    ) : task.action_text && href ? (
                      <nldd-button-group>
                        <Button
                          text={task.action_text}
                          appearance="primary"
                          onClick={() => {
                            onClose();
                            navigate(href);
                          }}
                        />
                      </nldd-button-group>
                    ) : href && task.status !== 'done' && task.status !== 'obsolete' ? (
                      <nldd-link href={href} text="Ga naar de plek van het werk" size="md" />
                    ) : null}
                  </Stack>
                  <Facts
                    label={`Over de taak ${title}`}
                    facts={taskFacts(task)}
                    labelWidth="120px"
                  />
                  {notes.length > 0 && (
                    <Stack gap="related">
                      {notes.map((item) => (
                        <Stack key={item.id} gap="tight">
                          <nldd-text>{item.body}</nldd-text>
                          <Quiet>
                            {[item.author_name, formatDate(item.created_at)]
                              .filter(Boolean)
                              .join(' · ')}
                          </Quiet>
                        </Stack>
                      ))}
                    </Stack>
                  )}
                  {writing ? (
                    <Stack gap="related">
                      <TextInput label="Notitie" value={note} onChange={setNote} multiline />
                      <nldd-button-group>
                        <Button
                          text="Bewaar notitie"
                          loading={save.isPending}
                          onClick={() => {
                            if (note.trim() === '') setError('Schrijf eerst een notitie.');
                            else save.mutate();
                          }}
                        />
                      </nldd-button-group>
                    </Stack>
                  ) : (
                    <nldd-button-group>
                      <Button
                        text="Schrijf een notitie"
                        appearance="neutral-transparent"
                        onClick={() => setWriting(true)}
                      />
                    </nldd-button-group>
                  )}
                </>
              )}
            </Stack>
          </RouterLinks>
        </nldd-simple-section>
      </nldd-page>
    </nldd-sheet>,
    document.body,
  );
}
