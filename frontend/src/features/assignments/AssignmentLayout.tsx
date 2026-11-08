import { PageBoundary } from '@/PageBoundary';
import { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Outlet, useLocation, useParams } from 'react-router-dom';
import { fetchCaseTasks, TASK_KEYS } from '@/features/tasks/api';
import { useCaseCourse } from '@/features/tasks/course';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { LoadError, Loading, Page } from '@/ui/layout';
import { assignmentKeys, fetchAssignment } from './api';
import { fetchAssignmentParts } from './partsApi';
import { AssignmentFrameContext, AssignmentShellContext, withOwnTask } from './shell';

/**
 * Loads what every page under an assignment needs and hands it down. It draws
 * no head: the landing and each part have their own.
 */
export function AssignmentLayout() {
  const { assignmentId = '' } = useParams();
  const { pathname } = useLocation();
  const instance = useInstance();
  const queryClient = useQueryClient();
  const assignment = useQuery({
    queryKey: assignmentKeys.detail(assignmentId),
    queryFn: () => fetchAssignment(assignmentId),
    enabled: assignmentId !== '',
    retry: false,
  });
  const parts = useQuery({
    queryKey: assignmentKeys.parts(assignmentId),
    queryFn: () => fetchAssignmentParts(assignmentId),
    enabled: assignmentId !== '',
    retry: false,
  });
  const course = useCaseCourse('assignment', assignmentId, assignment.data !== undefined);
  const next = course.data?.course?.next;
  // Only who runs the case or has a part in it can be told to wait while a
  // task of their own lies elsewhere in it.
  const mayHaveOtherWork =
    next !== undefined &&
    next !== null &&
    !next.mine &&
    (next.part === 'waits' || parts.data?.tasks_link === true);
  const tasks = useQuery({
    queryKey: TASK_KEYS.ofCase('assignment', assignmentId),
    queryFn: () => fetchCaseTasks('assignment', assignmentId),
    enabled: mayHaveOtherWork,
    retry: false,
  });

  // Any change made in this window can change what a row says.
  useEffect(
    () =>
      queryClient.getMutationCache().subscribe((event) => {
        if (event.type === 'updated' && event.mutation.state.status === 'success') {
          void queryClient.invalidateQueries({ queryKey: assignmentKeys.parts(assignmentId) });
        }
      }),
    [queryClient, assignmentId],
  );

  const ready =
    assignment.data !== undefined &&
    parts.data !== undefined &&
    !course.isPending &&
    // Only when asked for here: the page of all tasks reads the same query.
    !(mayHaveOtherWork && tasks.isLoading);

  if (!ready) {
    const failed = assignment.isError ? assignment : parts.isError ? parts : null;
    return (
      <Page
        kind="list"
        title="Opdracht"
        instanceName={instance?.name}
        back={{ href: PATHS.assignments, text: 'Terug naar Opdrachten' }}
      >
        {failed ? (
          <LoadError
            error={failed.error}
            retry={() => void failed.refetch()}
            what="Deze opdracht"
          />
        ) : (
          <Loading />
        )}
      </Page>
    );
  }
  return (
    <AssignmentShellContext.Provider value={assignment.data}>
      <AssignmentFrameContext.Provider
        value={{
          parts: parts.data,
          course: withOwnTask(course.data?.course, tasks.data?.tracks ?? []),
        }}
      >
        <PageBoundary resetKey={pathname}>
          <Outlet />
        </PageBoundary>
      </AssignmentFrameContext.Provider>
    </AssignmentShellContext.Provider>
  );
}
