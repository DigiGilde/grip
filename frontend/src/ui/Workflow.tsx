/**
 * Where a case stands, whose move it is and what that person does next.
 *
 * The server decides all of it from the same facts that open and close the
 * tasks (`/api/tasks/cases/.../course`); these pieces only draw the answer.
 * Three pieces, three places on a page:
 *
 *   CourseNow     the sentence about what happens now: first, under the title
 *   courseAction  the one next step for the page's primary button
 *   CourseLine    the step it is at and the one after, quiet: it informs and never competes
 *
 * A list says the same in one line with `courseLine`.
 */
import { formatDate } from '@/lib/format';
import { courseBrief, type Course, type CourseNext } from './course';
import './workflow.css';

/** "Vóór 15 okt 2026", or that the date has passed. */
function dueWords(next: CourseNext): string | null {
  if (!next.due_on) return null;
  const day = formatDate(next.due_on);
  return next.overdue ? `Had klaar moeten zijn op ${day}` : `Vóór ${day}`;
}

interface CourseNowProps {
  course: Course;
  /** Where the other open tasks of the case are listed. */
  tasksHref?: string;
}

/**
 * What happens now, in one sentence addressed to the reader, with what still
 * stands in the way. Nothing once the case has ended or nothing is open.
 */
export function CourseNow({ course, tasksHref }: CourseNowProps) {
  const next = course.next;
  if (course.ended || !next) return null;
  const due = dueWords(next);
  const missing = next.missing ?? [];
  const more = course.more_to_do ?? 0;
  return (
    <div
      className="course-now"
      data-mine={next.mine ? 'true' : 'false'}
      data-part={next.part ?? (next.mine ? 'acts' : 'waits')}
    >
      <nldd-text>{next.blocked ?? next.sentence}</nldd-text>
      {missing.length > 0 && (
        <nldd-text size="sm" color="secondary">
          {`Ontbreekt nog: ${missing.join(', ')}.`}
        </nldd-text>
      )}
      {(due || (more > 0 && tasksHref)) && (
        <div className="course-now-meta">
          {due && (
            <nldd-text size="sm" color={next.overdue ? 'critical' : 'secondary'}>
              {due}
            </nldd-text>
          )}
          {more > 0 && tasksHref && (
            <nldd-link
              href={tasksHref}
              size="sm"
              text={more === 1 ? 'En nog 1 taak voor jou' : `En nog ${more} taken voor jou`}
            />
          )}
        </div>
      )}
    </div>
  );
}

interface CourseLineProps {
  course: Course;
  accessibleLabel: string;
}

/**
 * Where the course is, in one line: the step it is at and the one after.
 * A step says its own state, so work done out of order still reads right.
 */
export function CourseLine({ course, accessibleLabel }: CourseLineProps) {
  const brief = courseBrief(course);
  if (!brief) return null;
  return (
    <nldd-text size="sm" color="secondary" role="group" aria-label={accessibleLabel}>
      <strong>{brief.now}</strong>
      {`, ${brief.then}`}
    </nldd-text>
  );
}
