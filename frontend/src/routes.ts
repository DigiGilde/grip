import { PATHS } from './paths';

export interface AppRoute {
  path: string;
  /** Page heading, navigation label and document title. */
  title: string;
  /** An nldd-icon name, shown in the bottom bar on small screens. */
  icon: string;
}

/**
 * The screens behind the login, in navigation order. Each is a placeholder
 * until its screen is built; the route table is what the navigation, the
 * router and the tests all read.
 */
export const APP_ROUTES: readonly AppRoute[] = [
  { path: PATHS.statusOverview, title: 'Stand van zaken', icon: 'home' },
  { path: PATHS.assignments, title: 'Opdrachten', icon: 'folder' },
  { path: PATHS.allocations, title: 'Inzet', icon: 'calendar' },
  { path: PATHS.costs, title: 'Kosten en facturen', icon: 'euro-sign' },
  { path: PATHS.rates, title: 'Tarieven', icon: 'coins' },
  { path: PATHS.team, title: 'Team', icon: 'team' },
  { path: PATHS.vacancies, title: 'Vacatures', icon: 'person-badge-plus' },
  { path: PATHS.reports, title: 'Rapportage', icon: 'chart-line' },
  { path: PATHS.client, title: 'Aanvragen', icon: 'paper-plane' },
  { path: PATHS.admin, title: 'Beheer', icon: 'gear' },
];

/** Exact match for the start page, prefix match for the rest. */
export function isCurrentRoute(routePath: string, pathname: string): boolean {
  if (routePath === '/') return pathname === '/';
  return pathname === routePath || pathname.startsWith(`${routePath}/`);
}
