import { useMemo } from 'react';
import { useAuth } from '@/auth/context';
import type { AuthPerson } from '@/api/auth';
import type { Viewer } from '@/routes';

/** Fixed order and words for the rights a person can hold in grip. */
const RIGHT_WORDS: readonly (readonly [string, string])[] = [
  ['beheerder', 'beheerder'],
  ['planner', 'planner'],
  ['lezer', 'lezer'],
  ['aanvrager', 'aanvrager'],
  ['tekenbevoegde', 'tekenbevoegde'],
  ['offertegoedkeurder', 'interne goedkeurder van offertes'],
  ['assignment_manager', 'eigenaar of manager van opdrachten'],
  ['line_manager', 'leidinggevende'],
  ['team_member', 'teamlid op opdrachten'],
];

/**
 * As what someone looks at grip, in words: the rights held and what follows
 * from the data. One sentence part, to stand under the name.
 */
export function viewerWords(viewer: Viewer): string {
  const held = new Set([...viewer.functions, ...viewer.relations]);
  const words = RIGHT_WORDS.filter(([name]) => held.has(name)).map(([, word]) => word);
  if (words.length === 0) return 'Geen rechten in grip';
  const text = words.join(', ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

interface CurrentViewer extends Viewer {
  person: AuthPerson | null;
}

/** The person behind the session, with the rights and relations the bar reads. */
export function useViewer(): CurrentViewer {
  const { state } = useAuth();
  return useMemo(() => {
    if (state.status !== 'authenticated') return { person: null, functions: [], relations: [] };
    return { person: state.person, functions: state.functions, relations: state.relations ?? [] };
  }, [state]);
}
