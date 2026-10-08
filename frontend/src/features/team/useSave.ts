import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';

/** Runs a change, refreshes everything about the team, and keeps the error of a failed one. */
export function useSave(onDone?: () => void) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ['team'] });
      onDone?.();
    },
    onError: (err) => setError(errorMessage(err)),
  });
  return { run: mutation.mutate, pending: mutation.isPending, error, setError };
}
