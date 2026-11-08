import { useQuery } from '@tanstack/react-query';
import { NewUpdates } from '@/features/history/NewUpdates';
import { SearchField } from '@/features/search/SearchField';
import { useInstance } from '@/layout/useInstance';
import { LoadError, Loading, Page, useNarrow } from '@/ui/layout';
import { START_KEYS, fetchStart } from './api';
import {
  ConnectionsBlock,
  FiguresBlock,
  MyAssignmentsBlock,
  MyPeopleBlock,
  MyRequestsBlock,
  MyWorkBlock,
  PlanningBlock,
  ToDoBlock,
} from './blocks';

/**
 * Start: what is there for the reader, in one column. What to do, then what
 * concerns this reader, then what is new. A block is only there when it holds
 * something for this reader.
 */
export function StartPage() {
  const instance = useInstance();
  const narrow = useNarrow();
  const query = useQuery({ queryKey: START_KEYS.all, queryFn: fetchStart });
  const start = query.data;
  return (
    <>
      {narrow && (
        <nldd-simple-section width="full" padding-bottom="0">
          <SearchField />
        </nldd-simple-section>
      )}
      <Page kind="list" spacing="sections" title="Start" instanceName={instance?.name}>
        {query.isPending && <Loading />}
        {query.isError && <LoadError error={query.error} retry={() => void query.refetch()} />}
        {start && (
          <>
            <ToDoBlock to_do={start.to_do} />
            {start.my_work && <MyWorkBlock block={start.my_work} />}
            {start.planning && <PlanningBlock block={start.planning} />}
            {start.my_assignments && <MyAssignmentsBlock block={start.my_assignments} />}
            {start.my_people && <MyPeopleBlock block={start.my_people} />}
            {start.figures && <FiguresBlock block={start.figures} />}
            {start.my_requests && <MyRequestsBlock block={start.my_requests} />}
            {start.connections && <ConnectionsBlock block={start.connections} />}
            <NewUpdates limit={3} />
          </>
        )}
      </Page>
    </>
  );
}
