/**
 * The two views of the Vacatures page: every vacancy the reader may see with
 * where it stands, and the vacancies that are published with their text. Each
 * view has its own address and stands as a tab under the title.
 */
import { PATHS } from '@/paths';
import type { PageTabs } from '@/ui/layout';

export type VacancyView = 'list' | 'published';

export function vacancyViewTabs(current: VacancyView): PageTabs {
  return {
    label: 'Weergave van de vacatures',
    current,
    narrow: 'bar',
    items: [
      { key: 'list', text: 'Alle vacatures', href: PATHS.vacancies },
      { key: 'published', text: 'Opengesteld', href: PATHS.vacancyPublished },
    ],
  };
}
