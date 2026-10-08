import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { orUndef } from '@/components/nldd/events';
import { TASK_KEYS, fetchTaskCounts } from '@/features/tasks/api';
import { PATHS } from '@/paths';
import { APP_ROUTES, isCurrentRoute, type AppRoute } from '@/routes';
import { useRouterLinks } from './useRouterLinks';

/**
 * The label of a section. "Taken" carries the number of open tasks that are
 * the reader's own, so the work shows without opening the page.
 */
function useRouteLabel(): (route: AppRoute) => string {
  const counts = useQuery({
    queryKey: TASK_KEYS.count,
    queryFn: fetchTaskCounts,
    refetchInterval: 60_000,
    retry: false,
  });
  const open = counts.data?.open ?? 0;
  return (route) => (route.path === PATHS.tasks && open > 0 ? `${route.title} (${open})` : route.title);
}

interface MainNavigationProps {
  /** Icons with the label underneath, for the bottom bar on small screens. */
  withIcons?: boolean;
}

/** The sections of the application as tabs, for the main toolbar. */
export function MainNavigation({ withIcons }: MainNavigationProps) {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  useRouterLinks(ref);
  const label = useRouteLabel();

  return (
    <nldd-tab-bar ref={ref} navigation accessible-label="Hoofdnavigatie">
      {APP_ROUTES.map((route) => (
        <nldd-tab-bar-item
          key={route.path}
          href={route.path}
          text={label(route)}
          {...(withIcons ? { icon: route.icon } : {})}
          current={orUndef(isCurrentRoute(route.path, pathname))}
        />
      ))}
    </nldd-tab-bar>
  );
}

/** The same sections for the toolbar's overflow menu, where the tabs go when they do not fit. */
export function MainNavigationOverflow() {
  const ref = useRef<HTMLElement>(null);
  useRouterLinks(ref);
  const label = useRouteLabel();

  return (
    <nldd-menu-group ref={ref} slot="overflow" text="Hoofdnavigatie">
      {APP_ROUTES.map((route) => (
        <nldd-menu-item key={route.path} href={route.path} icon={route.icon} text={label(route)} />
      ))}
    </nldd-menu-group>
  );
}
