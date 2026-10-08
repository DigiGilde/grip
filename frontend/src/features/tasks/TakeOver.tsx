/**
 * Doing a step for the one whose move it is. Offered to who runs the case
 * and is not at move: the task becomes theirs, a note on the task says from
 * whom, and the head then shows the step as their own.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost, errorMessage } from '@/api/client';
import { Button } from '@/ui/Button';
import type { Course } from '@/ui/course';
import { ErrorNotice } from '@/ui/layout';

export function TakeOverButton({ course }: { course: Course | null | undefined }) {
  const queryClient = useQueryClient();
  const next = course?.next;
  const take = useMutation({
    mutationFn: (taskId: string) => apiPost(`/api/tasks/${taskId}/takeover`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  });
  if (!next?.may_take_over || !next.task_id) return null;
  const taskId = next.task_id;
  return (
    <>
      {take.isError && <ErrorNotice message={errorMessage(take.error)} />}
      <nldd-button-group>
        <Button
          size="sm"
          text="Neem deze stap over"
          loading={take.isPending}
          onClick={() => take.mutate(taskId)}
        />
      </nldd-button-group>
    </>
  );
}
