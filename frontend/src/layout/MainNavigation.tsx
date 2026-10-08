import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { orUndef } from '@/components/nldd/events';
import { TASK_KEYS, fetchTaskCounts } from '@/features/tasks/api';
import { PATHS } from '@/paths';
import { currentRoute, navLabel, routesFor, type AppRoute } from '@/routes';
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
  // What the reader must do now. A task that waits on someone else is not counted.
  const toDo = counts.data?.to_do ?? 0;
  return (route) =>
    route.path === PATHS.tasks && toDo > 0
      ? { count: toDo, words: toDo === 1 ? '1 taak te doen' : `${toDo} taken te doen` }
      : null;
}

interface MainNavigationProps {
  /** Which sections: the work (the default), or the settings that sit apart at the end. */
  area?: AppRoute['area'];
  /** The name of the landmark; two navigation regions on a page need two names. */
  label?: string;
}

/**
 * The sections of the application as links in a menu bar, for a wide screen.
 *
 * A menu bar and not tabs: these are links to other pages, so each is a tab
 * stop of its own, Enter follows it and the one you are on carries
 * `aria-current="page"`. What does not fit goes behind the bar's own "Meer"
 * button, the last sections first.
 */
export function MainNavigation({ area = 'work', label = 'Hoofdnavigatie' }: MainNavigationProps) {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const viewer = useViewer();
  useRouterLinks(ref);
  const waiting = useWaiting();
  const routes = routesFor(viewer, area);
  const current = currentRoute(pathname);
  if (routes.length === 0) return null;

  return (
    <nldd-menu-bar
      ref={ref}
      className="main-navigation"
      accessible-label={label}
      overflow-text="Meer"
    >
      {routes.map((route) => {
        const waits = waiting(route);
        return (
          <nldd-menu-bar-item
            key={route.path}
            href={route.path}
            text={navLabel(route)}
            current={orUndef(route === current)}
            {...(waits ? { 'accessible-label': `${navLabel(route)}, ${waits.words}` } : {})}
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

/** One section as an item of a menu; the one you are on stands out in bold. */
function SectionMenuItem({ route, current }: { route: AppRoute; current: boolean }) {
  const waits = useWaiting()(route);
  return (
    <nldd-menu-item
      href={route.path}
      icon={route.icon}
      text={current ? `**${navLabel(route)}**` : navLabel(route)}
      {...(waits ? { details: String(waits.count) } : {})}
    />
  );
}

/**
 * All sections behind one button, for a screen too narrow for the bar. The
 * button names the section you are in, so the bar still says where you are.
 */
export function NavigationMenuButton() {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const viewer = useViewer();
  useRouterLinks(ref);
  const waiting = useWaiting();
  const current = currentRoute(pathname);
  const work = routesFor(viewer, 'work');
  const settings = routesFor(viewer, 'settings');
  const waits = work.map(waiting).find((entry) => entry !== null);

  const label = current ? navLabel(current) : 'Menu';
  return (
    <span className="navigation-menu-button">
      <nldd-button
        appearance="neutral-tinted"
        start-icon="list"
        text={label}
        accessible-label={`Menu, je bent bij ${current ? label : 'een pagina buiten het menu'}${
          waits ? `, ${waits.words}` : ''
        }`}
        max-width="220px"
        single-line
        expandable
      >
        <nldd-menu ref={ref} slot="popup" placement="bottom-start">
          {work.map((route) => (
            <SectionMenuItem key={route.path} route={route} current={route === current} />
          ))}
          {settings.length > 0 && (
            <nldd-menu-group text="Instellingen">
              {settings.map((route) => (
                <SectionMenuItem key={route.path} route={route} current={route === current} />
              ))}
            </nldd-menu-group>
          )}
        </nldd-menu>
      </nldd-button>
      {waits && <nldd-badge size="sm" color="accent" number={waits.count} decorative />}
    </span>
  );
}

/** The sections for a toolbar's overflow menu, where they go when the bar itself does not fit. */
export function MainNavigationOverflow({ area }: { area?: AppRoute['area'] }) {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const viewer = useViewer();
  useRouterLinks(ref);
  const routes = routesFor(viewer, area);
  const current = currentRoute(pathname);
  if (routes.length === 0) return null;

  return (
    <nldd-menu-group
      ref={ref}
      slot="overflow"
      text={area === 'settings' ? 'Instellingen' : 'Hoofdnavigatie'}
    >
      {routes.map((route) => (
        <SectionMenuItem key={route.path} route={route} current={route === current} />
      ))}
    </nldd-menu-group>
  );
}
