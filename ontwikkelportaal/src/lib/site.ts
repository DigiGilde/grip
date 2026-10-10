import { ROUTES } from './docs.mjs';

export { ROUTES };

export const SITE_NAME = 'Ontwikkelportaal van grip';

/** The organisations of the fictional chain, in the order of the chain. */
export const ORGANISATIONS = [
  'Voorbeeldministerie',
  'Voorbeeldprogramma',
  'DigiGilde voorbeeld',
  'Rijksorganisatie Voorbeeld ODI',
  'Voorbeeldbeheerorganisatie',
] as const;

export type Organisation = (typeof ORGANISATIONS)[number];

/** The code prefix of an organisation's personas: PRG for the programme. */
export const PREFIX: Record<Organisation, string> = {
  Voorbeeldministerie: 'MIN',
  Voorbeeldprogramma: 'PRG',
  'DigiGilde voorbeeld': 'GLD',
  'Rijksorganisatie Voorbeeld ODI': 'ODI',
  Voorbeeldbeheerorganisatie: 'BHO',
};

/** The overview with the filter on this organisation. */
export const orgRoute = (org: Organisation) => `${ROUTES.book}?organisatie=${PREFIX[org].toLowerCase()}`;

export const personaRoute = (code: string) => `${ROUTES.book}${code}/`;

export const ACCESS_LABELS: Record<string, string> = {
  account: 'Account',
  gast: 'Gast',
  'via-federatie': 'Via federatie',
};

export const STATUS_COLOR: Record<string, string> = {
  aanvaard: 'success',
  voorgesteld: 'warning',
  vervangen: 'neutral',
  afgewezen: 'critical',
};
