import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { TASK_KEYS, fetchTaskCounts } from '@/features/tasks';
import { keepInStep, showTaskCount } from './api';

/**
 * The number on the application's icon: the tasks that are yours to do, the
 * same number as the badge in the navigation. Also keeps this browser's
 * subscription in step with what grip knows, once per visit.
 */
export function useAppBadge(): void {
  const { data } = useQuery({ queryKey: TASK_KEYS.count, queryFn: fetchTaskCounts });
  const count = data?.to_do;
  useEffect(() => {
    if (typeof count === 'number') void showTaskCount(count);
  }, [count]);
  useEffect(() => {
    void keepInStep();
  }, []);
}
