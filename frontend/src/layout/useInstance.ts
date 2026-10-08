import { useQuery } from '@tanstack/react-query';
import { fetchInstance, type InstanceInfo } from '@/api/instance';

export const INSTANCE_KEY = ['instance'] as const;

/** The instance this frontend belongs to; undefined until it has loaded. */
export function useInstance(): InstanceInfo | undefined {
  const { data } = useQuery({
    queryKey: INSTANCE_KEY,
    queryFn: fetchInstance,
    staleTime: Infinity,
    retry: 1,
  });
  return data;
}
