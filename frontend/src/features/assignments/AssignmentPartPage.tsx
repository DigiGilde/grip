import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useInstance } from '@/layout/useInstance';
import { Button } from '@/ui/Button';
import { NoAccess, Page, type PageKind } from '@/ui/layout';
import { PrimaryTakenContext } from '@/ui/primary';
import { assignmentPartPath, assignmentPath, type AssignmentPartKey } from './paths';
import { stepOnPart, useAssignmentFrame, useAssignmentShell } from './shell';

const TASKS_TITLE = 'Alle taken van deze opdracht';

interface AssignmentPartPageProps {
  part: Exclude<AssignmentPartKey, 'landing'>;
  kind: PageKind;
  /** The part's own main action, in the head, when the next step does not stand there. */
  action?: ReactNode;
  children: ReactNode;
}

/**
 * One part of an assignment as a page of its own: back to the assignment, the
 * part's name, the one button and on a wide screen the other parts. The server
 * says which parts the reader has; without a row there is no part.
 */
export function AssignmentPartPage({ part, kind, action, children }: AssignmentPartPageProps) {
  const assignment = useAssignmentShell();
  const frame = useAssignmentFrame();
  const instance = useInstance();
  const navigate = useNavigate();
  if (!assignment || !frame) return null;

  const back = {
    href: assignmentPath(assignment.id),
    text: `Terug naar ${assignment.name}`,
  };
  const rows = frame.parts.parts;
  const title =
    part === 'tasks'
      ? frame.parts.tasks_link
        ? TASKS_TITLE
        : null
      : (rows.find((row) => row.key === part)?.label ??
        // A running assignment has no report row yet, but whoever reads the money may open it.
        (part === 'report' && assignment.permissions.read_financial ? 'Rapport' : null));
  if (title === null) {
    return (
      <Page kind="list" title={assignment.name} instanceName={instance?.name} back={back}>
        <NoAccess who="Dit onderdeel is er voor jou niet, of nu nog niet." />
      </Page>
    );
  }

  const step = stepOnPart(frame.course, assignment.id, part);
  return (
    <Page
      kind={kind}
      title={title}
      tabName={`${title}, ${assignment.name}`}
      instanceName={instance?.name}
      back={back}
      action={
        step ? (
          <Button appearance="primary" text={step.text} onClick={() => navigate(step.href)} />
        ) : (
          action
        )
      }
      tabs={{
        label: `Onderdelen van ${assignment.name}`,
        current: part,
        narrow: 'hide',
        items: rows.map((row) => ({
          key: row.key,
          text: row.label,
          href: assignmentPartPath(assignment.id, row.key),
        })),
      }}
    >
      <PrimaryTakenContext.Provider value={step !== null}>{children}</PrimaryTakenContext.Provider>
    </Page>
  );
}
