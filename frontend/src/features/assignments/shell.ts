/**
 * What the pages under one assignment share: the assignment itself, the rows
 * its reader has, and where it stands.
 */
import { createContext, useContext } from 'react';
import type { Track } from '@/features/tasks/api';
import { courseAction, type Course } from '@/ui/course';
import type { AssignmentDetail } from './api';
import type { AssignmentParts } from './partsApi';
import { assignmentPartPath, type AssignmentPartKey } from './paths';

export const AssignmentShellContext = createContext<AssignmentDetail | null>(null);

/** The assignment these pages are about, or null when a page is rendered on its own. */
export function useAssignmentShell(): AssignmentDetail | null {
  return useContext(AssignmentShellContext);
}

export interface AssignmentFrame {
  parts: AssignmentParts;
  course: Course | null | undefined;
}

export const AssignmentFrameContext = createContext<AssignmentFrame | null>(null);

/** The rows and the course; both are loaded before a page under the assignment renders. */
export function useAssignmentFrame(): AssignmentFrame | null {
  return useContext(AssignmentFrameContext);
}

/**
 * The next step when it belongs in the head of this part: it leads here and
 * asks for something the address opens, like the sheet of a month. A step that
 * only names the part leaves the part's own button to do it.
 */
export function stepOnPart(
  course: Course | null | undefined,
  assignmentId: string,
  part: AssignmentPartKey,
): { text: string; href: string } | null {
  const step = courseAction(course);
  if (!step) return null;
  const [path, query] = step.href.split('?');
  return query && path === assignmentPartPath(assignmentId, part) ? step : null;
}

/**
 * A course follows one line of work, so it can tell a reader to wait while
 * they have a task on another line: a planner on a potential assignment waits
 * for the quote and has roles to fill. Their own task then is what is next.
 */
export function withOwnTask(
  course: Course | null | undefined,
  tracks: readonly Pick<Track, 'tasks'>[],
): Course | null | undefined {
  if (!course?.next || course.next.mine || course.ended) return course;
  const own = tracks.flatMap((track) => track.tasks).filter((task) => task.needs_me);
  const first = own[0];
  if (!first) return course;
  return {
    ...course,
    next: {
      mine: true,
      part: 'acts',
      headline: first.headline ?? first.title,
      sentence: first.instruction ?? first.headline ?? first.title,
      due_on: first.due_on ?? null,
      overdue: first.overdue ?? false,
      action_text: first.action_text ?? null,
      action_href: first.step_href ?? first.work_href ?? null,
      task_id: first.id,
    },
    more_to_do: own.length - 1,
  };
}
