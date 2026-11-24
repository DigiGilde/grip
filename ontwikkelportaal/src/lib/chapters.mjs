// The chapters of Documentatie: which document belongs where, in reading
// order. The only place this lives; the Markdown in docs/ knows nothing of it.
// Plain JavaScript so that scripts/check-site.mjs can read it too.
import { ROUTES } from './docs.mjs';

/**
 * @typedef {{ title?: string, docs: string[] }} ChapterGroup
 * @typedef {{ slug: string, title: string, description: string, groups: ChapterGroup[] }} Chapter
 */

/** A chapter's slug shares /documentatie/ with the document ids, so it may not equal one. @type {Chapter[]} */
export const CHAPTERS = [
  {
    slug: 'functioneel-ontwerp',
    title: 'Functioneel ontwerp',
    description: 'Wat grip doet: begrippen en rekenregels, rollen en toegang, taken, werkstromen, gebeurtenissen en meldingen.',
    groups: [
      {
        docs: ['domein', 'rollen', 'toegang', 'taken', 'werkstromen', 'gebeurtenissen', 'meldingen', 'organisaties'],
      },
    ],
  },
  {
    slug: 'vormgeving',
    title: 'Vormgeving',
    description: 'Hoe een scherm wordt opgebouwd, het merk, toegankelijkheid en de rondes op visuele hiërarchie.',
    groups: [
      { docs: ['ontwerp', 'merk', 'navigatie-evaluatie', 'toegankelijkheid', 'offerte-document', 'rondgang'] },
      { title: 'Visuele hiërarchie', docs: ['hierarchie/a', 'hierarchie/b', 'hierarchie/c', 'hierarchie/d'] },
    ],
  },
  {
    slug: 'techniek',
    title: 'Techniek',
    description: 'Hoe grip in elkaar zit: architectuur, beveiliging, bewijs, snelheid, inloggen en koppelingen.',
    groups: [
      {
        docs: [
          'architectuur',
          'beveiliging',
          'bewijs',
          'snelheid',
          'sso-rijk',
          'passkeys-en-installeren',
          'wies',
          'import-grist',
          'vacatureteksten',
        ],
      },
    ],
  },
  {
    slug: 'lokaal-en-uitrol',
    title: 'Lokaal en uitrol',
    description: 'Grip lokaal draaien, uitrollen op het platform en verder werken op een andere machine.',
    groups: [{ docs: ['lokaal', 'uitrol-zad', 'overdracht'] }],
  },
  {
    slug: 'project',
    title: 'Project',
    description: 'De stand van het werk: wat er gebouwd is, wat niet, en wat op een beslissing of antwoord wacht.',
    groups: [{ docs: ['plan', 'openstaand'] }],
  },
];

export const chapterRoute = (/** @type {Chapter} */ chapter) => `${ROUTES.docs}${chapter.slug}/`;

export const docRoute = (/** @type {string} */ id) => `${ROUTES.docs}${id}/`;

/** The documents of a chapter in reading order. */
export const chapterDocs = (/** @type {Chapter} */ chapter) => chapter.groups.flatMap((g) => g.docs);

/** The chapter of a document, or undefined when it has none. */
export const chapterOf = (/** @type {string} */ id) => CHAPTERS.find((c) => chapterDocs(c).includes(id));
