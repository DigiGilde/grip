import { PATHS } from '@/paths';
import type { TextFact } from '@/ui/text/facts';
import { vacancyPartPath } from './paths';

/** Where a fact of a vacancy text is filled in. */
export function factHref(vacancyId: string, fact: Pick<TextFact, 'where'>): string {
  if (fact.where === 'settings') return PATHS.vacancyStandardTexts;
  if (fact.where === 'sender') return PATHS.quoteSender;
  return vacancyPartPath(vacancyId, 'request');
}
