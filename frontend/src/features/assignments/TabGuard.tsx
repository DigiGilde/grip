/**
 * A tab of an assignment only renders for a reader who has that tab.
 *
 * The shell leaves a tab out when the reader may not see what is on it, but
 * its address still exists: a link from elsewhere or a typed address lands
 * there. The server refuses the data; this says so before the tab shows any
 * action or sentence of its own.
 */
import type { ReactNode } from 'react';
import { NoAccess } from '@/ui/layout';
import { assignmentTabPath, type AssignmentTabKey } from './paths';
import { useAssignmentShell, visibleTabs } from './shell';

const FOR_WHOM: Partial<Record<AssignmentTabKey, string>> = {
  finance:
    'De bedragen van deze opdracht zijn voor de eigenaar, een manager, de beheerder en een lezer.',
  budget:
    'De begroting van deze opdracht is voor de eigenaar, een manager, de beheerder en een lezer.',
  quote:
    'De offertes van deze opdracht zijn voor de eigenaar, een manager, de beheerder en een lezer.',
  monthClose:
    'Afsluiten en factureren is voor de eigenaar, een manager, de beheerder en een lezer.',
  staffing: 'De bemensing is voor wie op deze opdracht werkt, haar beheert of plant.',
};

export function AssignmentTab({ tab, children }: { tab: AssignmentTabKey; children: ReactNode }) {
  const assignment = useAssignmentShell();
  if (assignment && !visibleTabs(assignment.permissions).includes(tab)) {
    return (
      // Inside the same section a tab's content sits in, so it shares its left edge.
      <nldd-simple-section>
        <NoAccess
          who={FOR_WHOM[tab]}
          back={{ text: 'Naar het overzicht', href: assignmentTabPath(assignment.id, 'overview') }}
        />
      </nldd-simple-section>
    );
  }
  return <>{children}</>;
}
