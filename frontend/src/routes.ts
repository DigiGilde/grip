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
  /**
   * The pages of this section that stand side by side, in the order of the
   * second bar. A section without views is one page.
   */
  views?: readonly SectionView[];
}

/** One of the sibling pages of a section. */
export interface SectionView {
  path: string;
  /** The word on the second bar and in the menu of a narrow screen. */
  title: string;
  /**
   * Who lands here when they choose the section. Without it, and for
   * everyone else, the section opens on its first view.
   */
  landingFor?: readonly string[];
}

/**
 * The sections of the application, in the order of the bar.
 *
 * Seven places for the work, each a word the reader uses: what comes to you
 * (the start and your tasks), the work itself (assignments, the people who do
 * it, the vacancies that bring them in), the money across assignments, and
 * looking back. The role of client shows only to who holds it. Settings come
 * last and sit apart.
 *
 * A section earns a place when someone needs it weekly and it is a place you
 * go to, not something reached from an assignment or a vacancy. Two pages
 * about one thing share a section and stand side by side as its views:
 * people and their deployment, costs and billing.
 */
export const APP_ROUTES: readonly AppRoute[] = [
  {
    path: PATHS.statusOverview,
    title: 'Stand van zaken',
    label: 'Start',
    icon: 'house',
    area: 'work',
  },
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
    path: PATHS.team,
    title: 'Team',
    icon: 'person-2',
    area: 'work',
    for: ['beheerder', 'planner', 'assignment_manager', 'line_manager'],
    views: [
      { path: PATHS.team, title: 'Mensen' },
      // The board is where a planner works every day.
      { path: PATHS.allocations, title: 'Inzet', landingFor: ['planner'] },
    ],
  },
  { path: PATHS.vacancies, title: 'Vacatures', icon: 'person-badge-plus', area: 'work' },
  {
    path: PATHS.costs,
    title: 'Financieel',
    icon: 'euro-sign',
    area: 'work',
    for: ['beheerder', 'lezer', 'assignment_manager'],
    views: [
      { path: PATHS.costs, title: 'Kosten' },
      { path: PATHS.billing, title: 'Factureren' },
    ],
  },
  {
    path: PATHS.reports,
    title: 'Rapportage',
    icon: 'chart-x-y-axis-line',
    area: 'work',
    for: ['beheerder', 'lezer', 'assignment_manager'],
  },
  {
    // The role of client. A beheerder without that role reaches it from Beheer.
    path: PATHS.client,
    title: 'Aanvragen',
    icon: 'paper-plane',
    area: 'work',
    for: ['aanvrager', 'tekenbevoegde'],
  },
  {
    path: PATHS.admin,
    title: 'Beheer',
    icon: 'gear',
    area: 'settings',
    for: ['beheerder'],
    // Reached from the Beheer page, whatever their address says.
    also: [PATHS.ratesLegacy, PATHS.vacancySetup, PATHS.vacancyStandardTexts],
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

/** Every address that belongs to a section: its own, its views and what it names besides. */
function sectionPaths(route: AppRoute): string[] {
  return [route.path, ...(route.views ?? []).map((view) => view.path), ...(route.also ?? [])];
}

/**
 * Where a section opens for this viewer: the view that is theirs to land on,
 * otherwise the first. The section stands in the same place for everyone;
 * only the page it opens on follows the reader's work.
 */
export function landingPath(route: AppRoute, viewer: Viewer): string {
  const held = new Set([...viewer.functions, ...viewer.relations]);
  const own = (route.views ?? []).find((view) => view.landingFor?.some((name) => held.has(name)));
  return own?.path ?? route.views?.[0]?.path ?? route.path;
}

/**
 * The view of a section a path belongs to, the longest match first, so a
 * deeper page keeps its view: a person under Mensen, a delivery under
 * Factureren.
 */
export function currentView(route: AppRoute, pathname: string): SectionView | undefined {
  return [...(route.views ?? [])]
    .sort((a, b) => b.path.length - a.path.length)
    .find((view) => isCurrentRoute(view.path, pathname));
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
