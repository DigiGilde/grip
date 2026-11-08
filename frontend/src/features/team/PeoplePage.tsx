import { useInstance } from '@/layout/useInstance';
import { Loading, Page } from '@/ui/layout';
import { PeopleView } from './PeopleView';
import { usePeopleViews } from './peopleTabs';

/** Mensen: who is on the team and how they are deployed. */
export function PeoplePage() {
  const instance = useInstance();
  const { tabs, pending } = usePeopleViews('list');
  return (
    <Page kind="worksheet" title="Mensen" instanceName={instance?.name} tabs={tabs}>
      {pending ? <Loading /> : <PeopleView />}
    </Page>
  );
}
