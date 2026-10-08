/**
 * The task API. A task is the work on an assignment or a vacancy: made by the
 * plan when something needs doing, and closed by the fact that it is done.
 * A list the reader has no right to is absent, not empty.
 */
import { apiGet, apiPatch, apiPost } from '@/api/client';
import { withLists } from '@/lib/absent';

export type CaseKind = 'assignment' | 'vacancy';
export type TaskStatus = 'todo' | 'doing' | 'waiting' | 'done' | 'obsolete';

export interface TaskNote {
  id: string;
  body: string;
  created_at: string;
  author_name?: string | null;
}

export interface ChecklistItem {
  text: string;
  done?: boolean;
}

export interface Task {
  id: string;
  case_kind: CaseKind;
  assignment_id?: string | null;
  /** Present when the reader may see the assignment. */
  assignment_name?: string | null;
  vacancy_id?: string | null;
  vacancy_title?: string | null;
  case_label: string;
  /** The title the plan gave the task. Show `headline` instead. */
  title: string;
  /** The task in a few words for this reader: what to do, or what is waited for. */
  headline?: string;
  /** What must happen, whoever reads it: for an overview of everyone's work. */
  doer_title?: string;
  /** The sentence addressed to this reader. */
  instruction?: string;
  /** The reader must act now; absent when the reader waits or only looks on. */
  needs_me?: boolean;
  /** What happened that made the task. */
  why?: string | null;
  /** What comes after it. */
  then?: string | null;
  /** The name of the one action; absent when the reader has nothing to do now. */
  action_text?: string | null;
  /** Where the work is done, inside the application. */
  work_href?: string | null;
  /** Who is waited on, when that is not the reader. */
  waits_on?: string | null;
  /** Nobody can do this until something outside the task changes. */
  blocked?: string | null;
  checklist?: ChecklistItem[];
  track: string;
  track_label: string;
  status: TaskStatus;
  status_label: string;
  origin: 'plan' | 'manual';
  due_on?: string | null;
  overdue?: boolean;
  assignee_person_id?: string | null;
  assignee_label: string;
  waiting_on?: string | null;
  /** The link the plan gave the task. Use `work_href` instead. */
  link?: string | null;
  is_mine?: boolean;
  can_change?: boolean;
  /** False for a task that only its fact closes. */
  can_complete?: boolean;
  closes_by_fact?: boolean;
  closing_fact_label?: string | null;
  completed_at?: string | null;
  completed_by_name?: string | null;
  completed_by_fact?: boolean;
  note_count?: number;
  notes?: TaskNote[];
}

export interface TaskCounts {
  open: number;
  to_do: number;
  overdue: number;
}

export interface TaskList {
  /** The reader's own tasks: to do, and waiting on someone else. */
  items: Task[];
  /** Tasks of others on the cases the reader started. */
  awaited: Task[];
  counts: TaskCounts;
}

export interface Track {
  key: string;
  label: string;
  open_count: number;
  waiting_count: number;
  /** Where the track stands, in one line. */
  standing: string;
  tasks: Task[];
}

export interface CaseTasks {
  case_kind: CaseKind;
  case_id: string;
  plan_version: string;
  can_add: boolean;
  tracks: Track[];
}

export interface NewTask {
  case_kind: CaseKind;
  case_id: string;
  title: string;
  track?: string;
  due_on?: string;
}

const BASE = '/api/tasks';
const NO_COUNTS: TaskCounts = { open: 0, to_do: 0, overdue: 0 };

export const TASK_KEYS = {
  all: ['tasks'] as const,
  mine: ['tasks', 'mine'] as const,
  count: ['tasks', 'count'] as const,
  board: ['tasks', 'board'] as const,
  ofCase: (kind: CaseKind, id: string) => ['tasks', 'case', kind, id] as const,
  detail: (id: string) => ['tasks', 'detail', id] as const,
};

function asList(body: Partial<TaskList>): TaskList {
  return {
    items: body.items ?? [],
    awaited: body.awaited ?? [],
    counts: { ...NO_COUNTS, ...body.counts },
  };
}

export const fetchMyTasks = async () => asList(await apiGet<Partial<TaskList>>(`${BASE}/mine`));
export const fetchTaskCounts = async (): Promise<TaskCounts> => ({
  ...NO_COUNTS,
  ...(await apiGet<Partial<TaskCounts>>(`${BASE}/count`)),
});
export const fetchBoard = async () =>
  asList(await apiGet<Partial<TaskList>>(BASE, { include_closed: true }));
export const fetchTask = (id: string) => apiGet<Task>(`${BASE}/${id}`);

export async function fetchCaseTasks(kind: CaseKind, id: string): Promise<CaseTasks> {
  const body = withLists(await apiGet<CaseTasks>(`${BASE}/cases/${kind}/${id}`), 'tracks');
  return { ...body, tracks: body.tracks.map((track) => withLists(track, 'tasks')) };
}

export const createTask = (task: NewTask) => apiPost<Task>(BASE, task);
export const setTaskStatus = (id: string, status: TaskStatus) =>
  apiPatch<Task>(`${BASE}/${id}`, { status });
export const addTaskNote = (id: string, body: string) =>
  apiPost<Task>(`${BASE}/${id}/notes`, { body });
