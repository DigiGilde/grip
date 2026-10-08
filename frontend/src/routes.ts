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
}

/**
 * The sections of the application, in the order of the bar.
 *
 * The order follows the work, not the order of building: first what comes to
 * you (the start and your tasks), then the work itself (assignments and who
 * does them), then looking at it (costs and reports), then the role of
 * client. Settings come last and sit apart.
 */
export const APP_ROUTES: readonly AppRoute[] = [
  { path: PATHS.statusOverview, title: 'Stand van zaken', icon: 'house', area: 'work' },
  {
    path: PATHS.tasks,
    title: 'Taken',
    icon: 'check-list',
    area: 'work',
    // Approving a quote is work that reaches you as a task.
    also: [PATHS.quoteApprovals],
  },
  {
    path: PATHS.assignments,
    title: 'Opdrachten',
    icon: 'folder',
    area: 'work',
    for: ['beheerder', 'lezer', 'planner', 'assignment_manager', 'team_member'],
  },
  {
    path: PATHS.allocations,
    title: 'Inzet',
    icon: 'calendar-event',
    area: 'work',
    for: ['beheerder', 'planner', 'assignment_manager', 'line_manager'],
  },
  { path: PATHS.vacancies, title: 'Vacatures', icon: 'person-badge-plus', area: 'work' },
  {
    path: PATHS.team,
    title: 'Team',
    icon: 'person-2',
    area: 'work',
    for: ['beheerder', 'planner', 'assignment_manager', 'line_manager'],
  },
  {
    path: PATHS.costs,
    title: 'Kosten en facturen',
    label: 'Kosten',
    icon: 'euro-sign',
    area: 'work',
    for: ['beheerder', 'lezer', 'assignment_manager'],
  },
  {
    path: PATHS.reports,
    title: 'Rapportage',
    icon: 'chart-x-y-axis-line',
    area: 'work',
    for: ['beheerder', 'lezer', 'assignment_manager'],
  },
  {
    path: PATHS.client,
    title: 'Aanvragen',
    icon: 'paper-plane',
    area: 'work',
    for: ['beheerder', 'aanvrager', 'tekenbevoegde'],
  },
  {
    path: PATHS.admin,
    title: 'Beheer',
    icon: 'gear',
    area: 'settings',
    for: ['beheerder'],
    // Reached from the Beheer page, whatever their address says.
    also: [PATHS.ratesLegacy, PATHS.vacancySetup],
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

/**
 * The section a path belongs to, or undefined for a page outside every
 * section. The longest matching prefix wins, so a page that lives under one
 * section's address but belongs to another can say so with `also`.
 */
export function currentRoute(pathname: string): AppRoute | undefined {
  let best: { route: AppRoute; length: number } | undefined;
  for (const route of APP_ROUTES) {
    for (const prefix of [route.path, ...(route.also ?? [])]) {
      if (isCurrentRoute(prefix, pathname) && (!best || prefix.length > best.length)) {
        best = { route, length: prefix.length };
      }
    }
  }
  return best?.route;
}
