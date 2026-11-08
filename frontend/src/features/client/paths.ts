import { PATHS } from '@/paths';

export const CLIENT_VIEWS = ['mijn', 'offertes', 'ontvangen'] as const;
export type ClientView = (typeof CLIENT_VIEWS)[number];

/** The overview, on one of its three views. */
export const clientPath = (view?: ClientView) =>
  view && view !== 'mijn' ? `${PATHS.client}?weergave=${view}` : PATHS.client;
export const clientAssignmentPath = (id: string) => `${PATHS.client}/opdracht/${id}`;
export const receivedQuotePath = (id: string) => `${PATHS.client}/offerte/${id}`;
