import { useState } from 'react';
import { useInstance } from '@/layout/useInstance';
import { Page } from '@/ui/layout';
import { KpiView } from './KpiView';
import { PeopleView } from './PeopleView';
import { Segments } from './ui/controls';

type View = 'people' | 'kpi';

/** The team: who is on it and how they are deployed, and the billability KPI per person. */
export function TeamPage() {
  const instance = useInstance();
  const [view, setView] = useState<View>('people');
  return (
    <Page title="Team" instanceName={instance?.name}>
      <Segments
        label="Weergave"
        value={view}
        onChange={(next) => setView(next === 'kpi' ? 'kpi' : 'people')}
        options={[
          { value: 'people', label: 'Personen' },
          { value: 'kpi', label: 'KPI per persoon' },
        ]}
      />
      {view === 'people' ? <PeopleView /> : <KpiView />}
    </Page>
  );
}
