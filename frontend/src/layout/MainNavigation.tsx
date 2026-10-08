import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { orUndef } from '@/components/nldd/events';
import { TASK_KEYS, fetchTaskCounts } from '@/features/tasks/api';
import { PATHS } from '@/paths';
import { currentRoute, routesFor, type AppRoute } from '@/routes';
import { useRouterLinks } from './useRouterLinks';
import { useViewer } from './useViewer';

/**
 * How much waits for the reader, per section. Only work that is the reader's
 * own earns a number: today that is the open tasks. Nothing waiting means no
 * number at all.
 */
function useWaiting(): (route: AppRoute) => { count: number; words: string } | null {
  const counts = useQuery({
    queryKey: TASK_KEYS.count,
    queryFn: fetchTaskCounts,
    refetchInterval: 60_000,
    retry: false,
  });
  const open = counts.data?.open ?? 0;
  return (route) =>
    route.path === PATHS.tasks && open > 0
      ? { count: open, words: open === 1 ? '1 open taak' : `${open} open taken` }
      : null;
}

interface MainNavigationProps {
  /** Which sections: the work, or the settings that sit apart at the end. */
  area: AppRoute['area'];
  /** The name of the landmark; two navigation regions on a page need two names. */
  label: string;
}

/**
 * The sections of the application as links in a menu bar.
 *
 * A menu bar and not tabs: these are links to other pages, so each is a tab
 * stop of its own, Enter follows it and the one you are on carries
 * `aria-current="page"`. What does not fit goes behind the bar's own "meer"
 * button, the last sections first.
 */
export function MainNavigation({ area, label }: MainNavigationProps) {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const viewer = useViewer();
  useRouterLinks(ref);
  const waiting = useWaiting();
  const routes = routesFor(viewer, area);
  const current = currentRoute(pathname);
  if (routes.length === 0) return null;

  return (
    <nldd-menu-bar ref={ref} accessible-label={label} overflow-text="Meer">
      {routes.map((route) => {
        const waits = waiting(route);
        return (
          <nldd-menu-bar-item
            key={route.path}
            href={route.path}
            text={route.title}
            current={orUndef(route === current)}
            {...(waits ? { 'accessible-label': `${route.title}, ${waits.words}` } : {})}
          >
            {waits && (
              <nldd-badge
                className="nav-count"
                size="sm"
                color="accent"
                number={waits.count}
                decorative
              />
            )}
          </nldd-menu-bar-item>
        );
      })}
    </nldd-menu-bar>
  );
}

/**
 * The same sections for the bottom bar of a small screen, as icons with a
 * label within reach of a thumb. All sections of the viewer, settings last.
 */
export function BottomNavigation() {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const viewer = useViewer();
  useRouterLinks(ref);
  const waiting = useWaiting();
  const current = currentRoute(pathname);

  return (
    <nldd-tab-bar ref={ref} navigation accessible-label="Hoofdnavigatie">
      {routesFor(viewer).map((route) => {
        const waits = waiting(route);
        return (
          <nldd-tab-bar-item
            key={route.path}
            href={route.path}
            text={waits ? `${route.title} (${waits.count})` : route.title}
            icon={route.icon}
            current={orUndef(route === current)}
          />
        );
      })}
    </nldd-tab-bar>
  );
}

/** The sections for a toolbar's overflow menu, where they go when the bar itself does not fit. */
export function MainNavigationOverflow({ area }: { area?: AppRoute['area'] }) {
  const ref = useRef<HTMLElement>(null);
  const viewer = useViewer();
  useRouterLinks(ref);
  const waiting = useWaiting();
  const routes = routesFor(viewer, area);
  if (routes.length === 0) return null;

  return (
    <nldd-menu-group ref={ref} slot="overflow" text={area === 'settings' ? 'Instellingen' : 'Hoofdnavigatie'}>
      {routes.map((route) => {
        const waits = waiting(route);
        return (
          <nldd-menu-item
            key={route.path}
            href={route.path}
            icon={route.icon}
            text={route.title}
            {...(waits ? { details: String(waits.count) } : {})}
          />
        );
      })}
    </nldd-menu-group>
  );
}
