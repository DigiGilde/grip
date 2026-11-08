import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { orUndef } from '@/components/nldd/events';
import { TASK_KEYS, fetchTaskCounts } from '@/features/tasks/api';
import { PATHS } from '@/paths';
import { currentRoute, landingPath, navLabel, routesFor, type AppRoute } from '@/routes';
import { useViewer } from './useViewer';
import './shell.css';

const PLACES = 'Plekken in Grip';
const SETTINGS = 'Instellingen';
const ME = 'Ik';
const ME_ICON = 'person-circle';

/** What the reader must do now. A task that waits on someone else is not counted. */
function useToDo(): number {
  const counts = useQuery({
    queryKey: TASK_KEYS.count,
    queryFn: fetchTaskCounts,
    refetchInterval: 60_000,
    retry: false,
  });
  return counts.data?.to_do ?? 0;
}

/**
 * A tab with an `accessible-label` of its own does not exist, so the name of
 * the bar is where a screen reader hears the number on the small screen.
 */
function placesLabel(toDo: number): string {
  if (toDo === 0) return PLACES;
  return `${PLACES}, ${toDo === 1 ? '1 taak' : `${toDo} taken`} te doen`;
}

/**
 * A key for the tab bar. The bar settles its tab stop when its tabs change, not
 * when `current` moves: going between a place and a page outside every place
 * would leave it without a tab stop, or with two. A new bar settles it again.
 */
function tabStopKey(hasCurrent: boolean): string {
  return hasCurrent ? 'current' : 'none';
}

/** The pages reached from Ik: the account as a page, and what its rows open. */
function isUnderMe(pathname: string, personId: string | undefined): boolean {
  const own = personId ? PATHS.person.replace(':personId', personId) : null;
  return [PATHS.me, PATHS.security, PATHS.notifications, own].includes(pathname);
}

/** The alternative for a toolbar's menu, for when a bar itself does not fit. */
function PlacesMenu({
  label,
  routes,
  here,
  toDo,
}: {
  label: string;
  routes: AppRoute[];
  here: AppRoute | undefined;
  toDo: number;
}) {
  const viewer = useViewer();
  return (
    <nldd-menu-group slot="overflow" text={label}>
      {routes.map((route) => (
        <nldd-menu-item
          key={route.path}
          href={landingPath(route, viewer)}
          icon={route.icon}
          text={route === here ? `**${navLabel(route)}**` : navLabel(route)}
          {...(route.path === PATHS.start && toDo > 0 ? { details: String(toDo) } : {})}
        />
      ))}
    </nldd-menu-group>
  );
}

/**
 * The places of the application in the top bar. The current place stays in the
 * bar when not everything fits; the bar has its own "Meer tabs" for the rest.
 */
export function MainNavigation() {
  const { pathname } = useLocation();
  const viewer = useViewer();
  const toDo = useToDo();
  const routes = routesFor(viewer, 'work');
  const here = currentRoute(pathname);

  const label = placesLabel(toDo);
  const item = useRef<HTMLElement>(null);
  // The toolbar does not notice a tab's text growing with the count and would
  // cut the words off. An attribute change on the item makes it measure again;
  // as a JSX prop React would set the property, which the toolbar does not watch.
  useEffect(() => item.current?.setAttribute('label', label), [label]);

  return (
    <nldd-toolbar-item ref={item} slot="start" priority={4}>
      <nldd-tab-bar
        key={tabStopKey(here !== undefined && routes.includes(here))}
        navigation
        accessible-label={label}
      >
        {routes.map((route) => (
          <nldd-tab-bar-item
            key={route.path}
            href={landingPath(route, viewer)}
            text={
              route.path === PATHS.start && toDo > 0
                ? `${navLabel(route)} (${toDo})`
                : navLabel(route)
            }
            current={orUndef(route === here)}
          />
        ))}
      </nldd-tab-bar>
      <PlacesMenu label={PLACES} routes={routes} here={here} toDo={toDo} />
    </nldd-toolbar-item>
  );
}

/** The settings of the instance, apart from the work, at the end of the top bar. */
export function SettingsNavigation() {
  const { pathname } = useLocation();
  const viewer = useViewer();
  const routes = routesFor(viewer, 'settings');
  const here = currentRoute(pathname);
  if (routes.length === 0) return null;

  return (
    <nldd-toolbar-item slot="end" priority={1}>
      <nldd-tab-bar
        key={tabStopKey(here !== undefined && routes.includes(here))}
        navigation
        accessible-label={SETTINGS}
      >
        {routes.map((route) => (
          <nldd-tab-bar-item
            key={route.path}
            href={landingPath(route, viewer)}
            text={navLabel(route)}
            current={orUndef(route === here)}
          />
        ))}
      </nldd-tab-bar>
      <PlacesMenu label={SETTINGS} routes={routes} here={here} toDo={0} />
    </nldd-toolbar-item>
  );
}

/**
 * The number on the corner of an icon: it takes no width, which is what keeps
 * every place in the bar on a phone. Decoration; the bar's name says it in words.
 */
function IconWithCount({ icon, count }: { icon: string; count: number }) {
  return (
    <span slot="icon" className="place-icon">
      <nldd-icon icon={icon} />
      <nldd-badge size="sm" color="inherit" number={count} decorative />
    </span>
  );
}

/** Every place as an icon with its word, at the bottom of a small screen, ending in Ik. */
export function BottomNavigation() {
  const { pathname } = useLocation();
  const viewer = useViewer();
  const toDo = useToDo();
  const routes = routesFor(viewer);
  const underMe = isUnderMe(pathname, viewer.person?.id);
  const here = underMe ? undefined : currentRoute(pathname);

  return (
    <nldd-toolbar-item slot="start" priority={1}>
      <nldd-tab-bar
        key={tabStopKey(underMe || here !== undefined)}
        navigation
        accessible-label={placesLabel(toDo)}
      >
        {routes.map((route) => {
          const counted = route.path === PATHS.start && toDo > 0;
          return (
            <nldd-tab-bar-item
              key={route.path}
              href={landingPath(route, viewer)}
              text={navLabel(route)}
              current={orUndef(route === here)}
              {...(counted ? {} : { icon: route.icon })}
            >
              {counted && <IconWithCount icon={route.icon} count={toDo} />}
            </nldd-tab-bar-item>
          );
        })}
        <nldd-tab-bar-item href={PATHS.me} text={ME} icon={ME_ICON} current={orUndef(underMe)} />
      </nldd-tab-bar>
      <nldd-menu-group slot="overflow" text={PLACES}>
        {routes.map((route) => (
          <nldd-menu-item
            key={route.path}
            href={landingPath(route, viewer)}
            icon={route.icon}
            text={navLabel(route)}
          />
        ))}
        <nldd-menu-item href={PATHS.me} icon={ME_ICON} text={ME} />
      </nldd-menu-group>
    </nldd-toolbar-item>
  );
}
