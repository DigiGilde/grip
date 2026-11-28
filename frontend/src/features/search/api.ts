/**
 * The search API: names of assignments, vacancies and people, each list
 * already cut down to what the reader may open.
 */
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/api/client';
import type { Phase } from '@/features/assignments/labels';

export const MIN_QUERY = 2;
export const MAX_QUERY = 100;

export interface SearchResults {
  q: string;
  assignments: { id: string; name: string; client_name: string | null; phase: Phase }[];
  vacancies: { id: string; title: string }[];
  people: { id: string; name: string }[];
}

/** What is searched for: the text without the spaces around it. */
export const cleanQuery = (text: string | null | undefined): string => (text ?? '').trim();

export const searchable = (q: string): boolean => q.length >= MIN_QUERY && q.length <= MAX_QUERY;

export function useSearch(q: string) {
  return useQuery({
    queryKey: ['search', q],
    queryFn: () => apiGet<SearchResults>('/api/search', { q }),
    enabled: searchable(q),
    retry: false,
  });
}
