import { PATHS } from './paths';

/** Who is looking: the rights held and the kinds of relation, as the session reports them. */
export interface Viewer {
  functions: readonly string[];
  relations: readonly string[];
}

export interface AppRoute {
  path: string;
  /** Page heading and document title, and the navigation label unless `label` is set. */
  title: string;
  /** A shorter word for the bar, where the page title would crowd out other sections. */
  label?: string;
  /** An nldd-icon name, shown in the bottom bar on small screens. */
  icon: string;
  /**
   * Where the section sits in the bar: with the work, or at the end with the
   * account, where the settings of the instance belong.
   */
  area: 'work' | 'settings';
  /**
   * Which rights or relations make the section worth offering. Without it the
   * section is for everyone. This only decides what the bar offers: the
   * server decides what a page shows, and a path typed by hand still opens.
   */
  for?: readonly string[];
  /** Paths outside `path` that belong to this section, for the current mark. */
  also?: readonly string[];
  /** Who opens this section elsewhere than on `path`, because that is where they work. */
  landing?: { path: string; for: readonly string[] };
}

/**
 * The sections of the application, in the order of the bar.
 *
 * What comes to you (the start, with your tasks in it), the work itself
 * (assignments, requests, vacancies and the people who do it) and the money
 * across assignments. The role of client shows only to who holds it. Settings
 * come last and sit apart.
 *
 * A section earns a place when someone needs it weekly and it is a place you
 * go to, not something reached from an assignment or a vacancy.
 */
export const APP_ROUTES: readonly AppRoute[] = [
  {
    path: PATHS.start,
    title: 'Start',
    icon: 'house',
    area: 'work',
    // Your tasks and what reaches you as one; the feed is reached from the start.
    also: [PATHS.tasks, PATHS.quoteApprovals, PATHS.updates],
  },
  {
    path: PATHS.assignments,
    title: 'Opdrachten',
    icon: 'folder',
    area: 'work',
    for: ['beheerder', 'lezer', 'planner', 'assignment_manager', 'team_member'],
  },
  {
    // The role of client. A beheerder without that role reaches it from Beheer.
    path: PATHS.client,
    title: 'Aanvragen',
    icon: 'paper-plane',
    area: 'work',
    for: ['aanvrager', 'tekenbevoegde'],
  },
  { path: PATHS.vacancies, title: 'Vacatures', icon: 'person-badge-plus', area: 'work' },
  {
    path: PATHS.people,
    title: 'Mensen',
    icon: 'person-2',
    area: 'work',
    for: ['beheerder', 'planner', 'assignment_manager', 'line_manager'],
    // The board is where a planner works every day.
    landing: { path: PATHS.peopleBoard, for: ['planner'] },
  },
  {
    path: PATHS.money,
    title: 'Geld',
    icon: 'euro-sign',
    area: 'work',
    for: ['beheerder', 'lezer', 'assignment_manager'],
  },
  {
    path: PATHS.admin,
    title: 'Beheer',
    icon: 'gear',
    area: 'settings',
    for: ['beheerder'],
    // Reached from the Beheer page, whatever their address says.
    also: [PATHS.vacancySetup, PATHS.vacancyStandardTexts],
  },
];

/** The word for a section in the bar. */
export function navLabel(route: AppRoute): string {
  return route.label ?? route.title;
}

/** The sections the bar offers this viewer, in order. */
export function routesFor(viewer: Viewer, area?: AppRoute['area']): AppRoute[] {
  const held = new Set([...viewer.functions, ...viewer.relations]);
  return APP_ROUTES.filter(
    (route) =>
      (area === undefined || route.area === area) &&
      (route.for === undefined || route.for.some((name) => held.has(name))),
  );
}

/** Exact match for the start page, prefix match for the rest. */
export function isCurrentRoute(routePath: string, pathname: string): boolean {
  if (routePath === '/') return pathname === '/';
  return pathname === routePath || pathname.startsWith(`${routePath}/`);
}

/** Every address that belongs to a section: its own and what it names besides. */
function sectionPaths(route: AppRoute): string[] {
  return [route.path, ...(route.also ?? [])];
}

/**
 * Where a section opens for this viewer. The section stands in the same place
 * for everyone; only the page it opens on follows the reader's work.
 */
export function landingPath(route: AppRoute, viewer: Viewer): string {
  const held = new Set([...viewer.functions, ...viewer.relations]);
  return route.landing?.for.some((name) => held.has(name)) ? route.landing.path : route.path;
}

/**
 * The section a path belongs to, or undefined for a page outside every
 * section. The longest matching prefix wins, so a page that lives under one
 * section's address but belongs to another can say so with `also`.
 */
export function currentRoute(pathname: string): AppRoute | undefined {
  let best: { route: AppRoute; length: number } | undefined;
  for (const route of APP_ROUTES) {
    for (const prefix of sectionPaths(route)) {
      if (isCurrentRoute(prefix, pathname) && (!best || prefix.length > best.length)) {
        best = { route, length: prefix.length };
      }
    }
  }
  return best?.route;
}
