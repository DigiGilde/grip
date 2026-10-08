import { useState } from 'react';
import { useAuth } from '@/auth/context';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import { KpiView } from './KpiView';
import { PeopleView } from './PeopleView';
import { Segments } from './ui/controls';

type View = 'people' | 'kpi';

/** The team: who is on it, and the billability KPI per person. */
export function TeamPage() {
  const instance = useInstance();
  const [view, setView] = useState<View>('people');
  const { state } = useAuth();
  const isBeheerder = state.status === 'authenticated' && state.functions.includes('beheerder');
  return (
    <nldd-simple-section>
      <PageHeading text="Team" instanceName={instance?.name} />
      <nldd-container gap="16">
        <Segments
          label="Weergave"
          value={view}
          onChange={(next) => setView(next === 'kpi' ? 'kpi' : 'people')}
          options={[
            { value: 'people', label: 'Personen' },
            { value: 'kpi', label: 'KPI per persoon' },
          ]}
        />
        {isBeheerder && (
          // Who gets access is decided here: the proposals from Wies add
          // and deactivate persons, and only the beheerder confirms them.
          <RouterLinks>
            <nldd-button
              href={PATHS.wiesProposals}
              text="Voorstellen uit Wies"
              appearance="secondary"
            />
          </RouterLinks>
        )}
        {view === 'people' ? <PeopleView /> : <KpiView />}
      </nldd-container>
    </nldd-simple-section>
  );
}
