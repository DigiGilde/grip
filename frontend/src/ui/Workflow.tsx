/**
 * Where a case stands, whose move it is and what that person does next.
 *
 * The server decides all of it from the same facts that open and close the
 * tasks (`/api/tasks/cases/.../course`); these pieces only draw the answer.
 * Three pieces, three places on a page:
 *
 *   CourseNow     the sentence about what happens now: first, under the title
 *   courseAction  the one next step for the page's primary button
 *   CourseBar     the steps, quiet: it informs and never competes
 *
 * A list says the same in one line with `courseLine`.
 */
import { formatDate } from '@/lib/format';
import { lowerFirst, type Course, type CourseNext } from './course';
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
    <div className="course-now" data-mine={next.mine ? 'true' : 'false'}>
      <nldd-text size="lg">{next.blocked ?? next.sentence}</nldd-text>
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

interface CourseBarProps {
  course: Course;
  accessibleLabel: string;
}

/**
 * The steps of the course. A step says its own state, so work done out of
 * order shows as done. A note says what happened at a step.
 */
export function CourseBar({ course, accessibleLabel }: CourseBarProps) {
  if (course.steps.length === 0) return null;
  // The sentence above the bar already says what holds for the current step.
  const notes = course.steps.filter((step) => step.note && step.state === 'done');
  return (
    <div className="course-bar">
      <nldd-step-bar accessible-label={accessibleLabel}>
        {course.steps.map((step) => (
          <nldd-step-bar-item
            key={step.key}
            text={step.label}
            status={step.state === 'done' ? 'past' : step.state}
          />
        ))}
      </nldd-step-bar>
      {notes.length > 0 && (
        <nldd-text size="sm" color="secondary">
          {notes.map((step) => `${step.label}: ${lowerFirst(step.note ?? '')}`).join(' · ')}
        </nldd-text>
      )}
    </div>
  );
}
