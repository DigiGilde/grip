/**
 * How a task is shown: its words for this reader, where its work is, and
 * which tasks are the reader's to do. Pure, so it is tested.
 */
import { formatDate } from '@/lib/format';
import type { Task } from './api';

/** The search parameter that says: this page was opened to do that task. */
export const FOR_TASK_PARAM = 'bij-taak';

/** What the task is called for this reader. */
export const headlineOf = (task: Task) => task.headline || task.title;

/**
 * Where the work of a task is done, with the task named in the address so
 * the page can say what the reader came to do.
 */
export function workHref(task: Task): string | null {
  const href = task.work_href ?? task.link;
  if (!href) return null;
  return `${href}${href.includes('?') ? '&' : '?'}${FOR_TASK_PARAM}=${task.id}`;
}

/** The address without the task, for when the bar is dismissed. */
export function withoutTask(search: string): string {
  const params = new URLSearchParams(search);
  params.delete(FOR_TASK_PARAM);
  const rest = params.toString();
  return rest ? `?${rest}` : '';
}

export interface AboutLink {
  text: string;
  href: string;
}

/** What the task is about, each as a link to the thing itself. */
export function aboutLinks(task: Task): AboutLink[] {
  const links: AboutLink[] = [];
  if (task.vacancy_id) {
    links.push({
      text: task.vacancy_title ? `Vacature ${task.vacancy_title}` : 'Vacature',
      href: `/vacatures/${task.vacancy_id}`,
    });
  }
  if (task.assignment_id && task.assignment_name) {
    links.push({ text: task.assignment_name, href: `/opdrachten/${task.assignment_id}` });
  }
  return links;
}

/** The same, as one quiet line for a row. */
export function aboutLine(task: Task): string {
  const names = aboutLinks(task).map((link) => link.text);
  return names.length > 0 ? names.join(' · ') : task.case_label;
}

/** By when, in words; a task without a date says nothing. */
export function dueWords(task: Task): string {
  if (!task.due_on) return '';
  return task.overdue
    ? `Te laat: vóór ${formatDate(task.due_on)}`
    : `Vóór ${formatDate(task.due_on)}`;
}

/** A task the reader finishes with one decision, in the sheet itself. */
export const finishesHere = (task: Task) => task.needs_me === true && task.can_complete === true;

/**
 * What activating a task in a list does: a task that is the reader's to do
 * goes to the place where it is done; any other opens to be read.
 */
export function goesToWork(task: Task): boolean {
  return task.needs_me === true && !finishesHere(task) && workHref(task) !== null;
}

function byDue(a: Task, b: Task): number {
  return (a.due_on ?? '9999').localeCompare(b.due_on ?? '9999');
}

export interface MyWork {
  /** What the reader must do now, the soonest first. */
  toDo: Task[];
  /** What the reader waits for: own tasks that wait, and tasks of others on the reader's cases. */
  waiting: Task[];
}

export function myWork(items: readonly Task[], awaited: readonly Task[] = []): MyWork {
  const toDo = items.filter((task) => task.needs_me === true).sort(byDue);
  const waiting = [...items.filter((task) => task.needs_me !== true), ...awaited].sort(byDue);
  return { toDo, waiting };
}
