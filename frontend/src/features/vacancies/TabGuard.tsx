/**
 * A tab of a vacancy only renders for a reader who has that tab; see the
 * same guard for an assignment.
 */
import type { ReactNode } from 'react';
import { NoAccess } from '@/ui/layout';
import { vacancyTabPath, type VacancyTabKey } from './paths';
import { useVacancyShell, visibleTabs } from './shell';

export function VacancyTab({ tab, children }: { tab: VacancyTabKey; children: ReactNode }) {
  const { vacancy } = useVacancyShell();
  if (!visibleTabs(vacancy).includes(tab)) {
    return (
      // Inside the same section a tab's content sits in, so it shares its left edge.
      <nldd-simple-section>
        <NoAccess
          who="Dit deel is voor wie de vacature beheert."
          back={{ text: 'Naar de aanvraag', href: vacancyTabPath(vacancy.id, 'request') }}
        />
      </nldd-simple-section>
    );
  }
  return <>{children}</>;
}
