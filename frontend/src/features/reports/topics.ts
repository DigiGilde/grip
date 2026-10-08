import { PATHS } from '@/paths';
import type { Steering } from './api';

/** The detail views under Rapportage: one topic, one question each. */
export const TOPICS = {
  omzet: { title: 'Omzet', block: 'turnover' },
  bezetting: { title: 'Bezetting', block: 'occupancy' },
  pijplijn: { title: 'Pijplijn', block: 'pipeline' },
  kosten: { title: 'Kosten', block: 'costs' },
  declarabiliteit: { title: 'Declarabiliteit', block: 'billability' },
  'open-rollen': { title: 'Open rollen', block: 'open_roles' },
  jaarverantwoording: { title: 'Jaarverantwoording', block: null },
} as const satisfies Record<string, { title: string; block: keyof Steering | null }>;

export type TopicSlug = keyof typeof TOPICS;

export const isTopic = (slug: string | undefined): slug is TopicSlug =>
  slug !== undefined && Object.hasOwn(TOPICS, slug);

/** The name of the year in the address, so a view can be linked to with its year. */
export const YEAR_PARAM = 'jaar';

const withYear = (path: string, year: string) => `${path}?${YEAR_PARAM}=${encodeURIComponent(year)}`;

export const reportsPath = (year: string) => withYear(PATHS.reports, year);

export const topicPath = (slug: TopicSlug, year: string) =>
  withYear(`${PATHS.reports}/${slug}`, year);
