import { useState } from 'react';
import { useInstance } from '@/layout/useInstance';
import type { ActionBarFilter } from '@/ui/ActionBar';
import { Page } from '@/ui/layout';
import { KpiView } from './KpiView';
import { PeopleView } from './PeopleView';

type View = 'people' | 'kpi';

const VIEWS = [
  // The second bar of the section already says "Mensen"; these are two ways
  // to look at the same people.
  { value: 'people', label: 'Inzet en tarief' },
  { value: 'kpi', label: 'Declarabiliteit' },
] as const;

/** The team: who is on it and how they are deployed, and the billability KPI per person. */
export function TeamPage() {
  const instance = useInstance();
  const [view, setView] = useState<View>('people');
  // The choice of view is a filter like any other: it stands first in the
  // one bar of the page, quiet, so the primary action is the only accent.
  const viewFilter: ActionBarFilter = {
    label: 'Weergave',
    value: view,
    onChange: (next) => setView(next === 'kpi' ? 'kpi' : 'people'),
    options: VIEWS,
    width: '200px',
  };
  return (
    <Page title="Team" instanceName={instance?.name}>
      {view === 'people' ? (
        <PeopleView viewFilter={viewFilter} />
      ) : (
        <KpiView viewFilter={viewFilter} />
      )}
    </Page>
  );
}
