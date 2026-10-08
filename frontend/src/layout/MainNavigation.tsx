import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { orUndef } from '@/components/nldd/events';
import { TASK_KEYS, fetchTaskCounts } from '@/features/tasks/api';
import { PATHS } from '@/paths';
import {
  currentRoute,
  currentView,
  landingPath,
  navLabel,
  routesFor,
  type AppRoute,
} from '@/routes';
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

/**
 * Keeps the section you are in out of the overflow.
 *
 * The menu bar puts what does not fit behind its button, the last items
 * first, and has no way to pin one. So when the current section ends up
 * there, it moves forward to the last place that still fits and the section
 * that stood there goes behind the button instead. The order is the natural
 * one again as soon as the bar changes width or the reader moves on.
 */
function useCurrentInView(
  ref: React.RefObject<HTMLElement | null>,
  routes: AppRoute[],
  current: AppRoute | undefined,
  pathname: string,
): AppRoute[] {
  const present = routes.length > 0;
  // One second look per page and width, so the order cannot flip back and forth.
  const retried = useRef(false);
  // The place the current section is moved to, or null for the natural order.
  const [place, setPlace] = useState<number | null>(null);
  useEffect(() => {
    const bar = ref.current;
    if (!bar) return;
    const check = () => {
      const items = [...bar.querySelectorAll('nldd-menu-bar-item')];
      const here = items.find((item) => item.hasAttribute('current'));
      if (!here) return;
      const fits = items.filter((item) => !item.hasAttribute('data-overflow')).length;
      if (!here.hasAttribute('data-overflow')) {
        // Moved forward while its own place fits after all (the first
        // measure came before the fonts): try the natural order once more.
        const own = Number(here.getAttribute('data-place'));
        if (items.indexOf(here) !== own && fits > own && !retried.current) {
          retried.current = true;
          setPlace(null);
        }
        return;
      }
      setPlace((was) => Math.max(0, (was === null ? fits : Math.min(was, fits)) - 1));
    };
    // The bar marks what it moved behind its button; that is the signal.
    const marks = new MutationObserver(check);
    marks.observe(bar, { subtree: true, attributes: true, attributeFilter: ['data-overflow'] });
    // A window that changes width: back to the natural order, and ask the bar
    // to measure again. It sizes itself to what it shows, so on its own it
    // does not notice that there is room again.
    const onResize = () => {
      retried.current = false;
      setPlace(null);
      (bar as HTMLElement & { requestOverflowUpdate?: () => void }).requestOverflowUpdate?.();
    };
    window.addEventListener('resize', onResize);
    check();
    return () => {
      marks.disconnect();
      window.removeEventListener('resize', onResize);
    };
    // The bar is only there once the reader is known: `present` runs this again then.
  }, [ref, present]);

  // Another page: start from the natural order. When the order already is
  // natural the bar does not measure again, so look at its marks directly.
  useEffect(() => {
    retried.current = false;
    setPlace((was) => {
      if (was !== null) return null;
      const bar = ref.current;
      const here = bar?.querySelector('nldd-menu-bar-item[current]');
      if (!bar || !here?.hasAttribute('data-overflow')) return null;
      const fits = bar.querySelectorAll('nldd-menu-bar-item:not([data-overflow])').length;
      return Math.max(0, fits - 1);
    });
  }, [pathname, ref]);

  return useMemo(() => {
    if (place === null || !current || !routes.includes(current)) return routes;
    const rest = routes.filter((route) => route !== current);
    const at = Math.min(place, routes.indexOf(current));
    return [...rest.slice(0, at), current, ...rest.slice(at)];
  }, [routes, current, place]);
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
  const offered = routesFor(viewer, area);
  const current = currentRoute(pathname);
  const routes = useCurrentInView(ref, offered, current, pathname);
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
            // Its place in the natural order, for when it is moved to stay in view.
            data-place={offered.indexOf(route)}
            href={landingPath(route, viewer)}
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

/**
 * One section as an item of a menu; the one you are on stands out in bold.
 * A section with views lists them beneath it, without an icon, so they read
 * as belonging to the section above.
 */
function SectionMenuItem({ route, current }: { route: AppRoute; current: boolean }) {
  const waits = useWaiting()(route);
  const viewer = useViewer();
  const { pathname } = useLocation();
  const here = current ? currentView(route, pathname) : undefined;
  return (
    <>
      <nldd-menu-item
        href={landingPath(route, viewer)}
        icon={route.icon}
        text={current ? `**${navLabel(route)}**` : navLabel(route)}
        {...(waits ? { details: String(waits.count) } : {})}
      />
      {(route.views ?? []).map((view) => (
        <nldd-menu-item
          key={view.path}
          className="section-view-item"
          href={view.path}
          text={view === here ? `**${view.title}**` : view.title}
          accessible-label={`${navLabel(route)}, ${view.title}`}
        />
      ))}
    </>
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

/**
 * The sibling pages of the section you are in, as a second bar under the
 * main one: Mensen and Inzet under Team, Kosten and Factureren under
 * Financieel. It is navigation, not content: the same kind of bar as the
 * main one, smaller and directly under it, the page you are on underlined.
 * No filled mark, so the page keeps its one accent for its primary action.
 * A deeper page keeps its view, which is why such a page needs no link back
 * to it. A section of one page has no second bar.
 */
export function SectionViews() {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  useRouterLinks(ref);
  const section = currentRoute(pathname);
  const views = section?.views ?? [];
  if (!section || views.length < 2) return null;
  const here = currentView(section, pathname);

  return (
    <nldd-simple-section className="section-views" padding-block="0">
      <nldd-menu-bar ref={ref} accessible-label={`Pagina's van ${navLabel(section)}`}>
        {views.map((view) => (
          <nldd-menu-bar-item
            key={view.path}
            href={view.path}
            text={view.title}
            current={orUndef(view === here)}
          />
        ))}
      </nldd-menu-bar>
    </nldd-simple-section>
  );
}
