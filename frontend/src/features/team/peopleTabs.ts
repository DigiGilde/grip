import { useQuery } from '@tanstack/react-query';
import { PATHS } from '@/paths';
import type { PageTabs } from '@/ui/layout';
import { fetchPeopleViews, peopleViewsKey, type PeopleViewName } from './api';

const VIEWS: Record<PeopleViewName, { text: string; href: string }> = {
  list: { text: 'Lijst', href: PATHS.people },
  board: { text: 'Bord', href: PATHS.peopleBoard },
  occupancy: { text: 'Bezetting', href: PATHS.peopleOccupancy },
  billability: { text: 'Declarabiliteit', href: PATHS.peopleBillability },
};

/**
 * The views of Mensen as the tabs of a page: only what the server says this
 * reader has, and nothing at all when it has not said or when there is one.
 * `pending` is true until the server has answered: a page holds its content
 * back until then, so the bar does not push it down.
 */
export function usePeopleViews(current: PeopleViewName): {
  tabs: PageTabs | undefined;
  pending: boolean;
} {
  const query = useQuery({ queryKey: peopleViewsKey, queryFn: fetchPeopleViews, retry: false });
  const views = query.data?.views ?? [];
  return {
    pending: query.isPending,
    tabs:
      views.length < 2
        ? undefined
        : {
            label: 'Weergave van Mensen',
            current,
            narrow: 'bar',
            items: views.map((key) => ({ key, ...VIEWS[key] })),
          },
  };
}
