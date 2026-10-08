/**
 * The course of a case as the server gives it, and what a list says of it.
 * The drawing is in `Workflow.tsx`.
 */
export interface CourseStep {
  key: string;
  label: string;
  state: 'done' | 'current' | 'future';
  /** What happened at this step, when that is worth saying. */
  note?: string | null;
}

export interface CourseNext {
  /** The reader must act; false when the reader waits or only looks on. */
  mine: boolean;
  headline: string;
  sentence: string;
  who?: string | null;
  since?: string | null;
  due_on?: string | null;
  overdue?: boolean;
  action_text?: string | null;
  action_href?: string | null;
  missing?: string[];
  blocked?: string | null;
  task_id?: string | null;
  /** The kind of work, for a screen that can do the step in place. */
  task_key?: string | null;
}

export interface Course {
  key: string;
  label: string;
  subject?: string;
  subject_key?: string;
  subject_label?: string | null;
  steps: CourseStep[];
  current_key?: string | null;
  current_label?: string | null;
  position?: string | null;
  next?: CourseNext | null;
  ended?: string | null;
  more_to_do?: number;
  more_waiting?: number;
}

/** The one next step, when it is the reader's move and leads somewhere. */
export function courseAction(course: Course | null | undefined): {
  text: string;
  href: string;
} | null {
  const next = course?.next;
  if (!next?.mine || !next.action_text || !next.action_href) return null;
  return { text: next.action_text, href: next.action_href };
}

export function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/** Where a case stands and whose move it is, as two short texts for a list. */
export function courseLine(course: Course | null | undefined): {
  step: string;
  who: string;
  mine: boolean;
  overdue: boolean;
} | null {
  if (!course) return null;
  if (course.ended) return { step: course.ended, who: '', mine: false, overdue: false };
  const next = course.next;
  const step = course.current_label ?? 'Afgerond';
  if (!next) return { step, who: '', mine: false, overdue: false };
  const who = next.mine
    ? `Jij: ${lowerFirst(next.headline)}`
    : next.who
      ? `Wacht op ${next.who}`
      : '';
  return { step, who, mine: next.mine, overdue: Boolean(next.overdue) };
}
