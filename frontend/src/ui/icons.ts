/**
 * The icon vocabulary of the application.
 *
 * An icon helps only when the same picture always means the same thing and
 * the same thing always gets the same picture. So features never name an
 * icon: they name a concept ("download", "back", "attention") and this file
 * decides the picture, where it stands and what an icon-only control says.
 *
 * The design system prefers text over icons, and so does this list: most
 * actions have no icon at all, because their verb says it. A concept is here
 * when the icon is required (an icon-only control, a link that leaves the
 * page, a download, a status) or when it is the fixed picture of a section.
 * The rules for placement are in docs/ontwerp.md under "Iconen"; the guard in
 * icons.guard.test.ts fails on an icon name written anywhere else.
 */

export interface IconSpec {
  /** A name from the design system's icon set. */
  icon: string;
  /** Before the label, or after it for the fixed cases that point onward. */
  position: 'start' | 'end';
  /** What an icon-only control with this concept is called; the name of what it acts on follows. */
  label?: string;
}

const start = (icon: string, label?: string): IconSpec => ({
  icon,
  position: 'start',
  ...(label ? { label } : {}),
});
const end = (icon: string, label?: string): IconSpec => ({
  icon,
  position: 'end',
  ...(label ? { label } : {}),
});

export const ICONS = {
  // Actions. Only those that need a picture: the rest is a verb on a button.
  /** The one quiet button that holds what else a row or card can do. */
  more: start('more', 'Meer acties'),
  /** Adding a new entry from inside a picker or list; never on a page's primary button. */
  add: start('plus', 'Voeg toe'),
  /** Removing, where there is no room for the word. In a menu the word and the destructive colour say it. */
  remove: start('trash', 'Verwijder'),
  /** A file that lands on the reader's device. */
  download: start('download', 'Download'),
  /** A file the reader hands over. */
  upload: start('upload', 'Upload'),
  /** Back to the section a page belongs to. */
  back: start('arrow-left', 'Terug'),
  /** Anything that opens outside this page: a new tab, a document, another site. */
  elsewhere: end('external-link', 'Open in een nieuw tabblad'),
  /** A row or item that opens what it stands for. */
  open: end('chevron-right', 'Open'),
  /** Closing a sheet or dialog. */
  close: start('close', 'Sluit'),
  /** Putting something on the clipboard, where there is no room for the word. */
  copy: start('copy', 'Kopieer'),
  /** Finding within a list. */
  search: start('search', 'Zoek'),
  /** Going back to an earlier state: withdrawing, returning to yourself. */
  undo: start('arrow-u-turn-backward', 'Maak ongedaan'),

  // Statuses and signals. One picture per status, wherever it shows.
  /** Done, settled, complete. */
  done: start('check-circle-filled', 'Klaar'),
  /** Not done yet, nothing wrong. */
  todo: start('circle', 'Nog te doen'),
  /** Waiting, on time or on someone else. */
  waiting: start('clock', 'Wacht'),
  /** Needs a person's attention: over budget, overdue, double booked. */
  attention: start('warning', 'Vraagt aandacht'),
  /** Went wrong. */
  error: start('error', 'Fout'),
  /** Worth knowing, nothing to do. */
  info: start('info-circle', 'Informatie'),
  /** Fixed and no longer changeable: a closed month, a made quote. */
  locked: start('lock', 'Vastgelegd'),

  // Objects. The picture of a thing is the picture of its section.
  start: start('house'),
  task: start('check-list'),
  assignment: start('folder'),
  staffing: start('calendar-event'),
  vacancy: start('person-badge-plus'),
  team: start('person-2'),
  cost: start('euro-sign'),
  report: start('chart-x-y-axis-line'),
  request: start('paper-plane'),
  settings: start('gear'),
  person: start('person'),
  account: start('person-circle', 'Account'),
  logout: start('logout'),
  menu: start('list', 'Menu'),
  document: start('document'),
  history: start('clock-arrow-counter-clockwise'),
  proof: start('seal-check-mark'),
  security: start('key'),
  notify: start('bell'),
  organisation: start('building'),
  node: start('tree-structure'),
  mail: start('mail'),
} as const satisfies Record<string, IconSpec>;

export type IconConcept = keyof typeof ICONS;

/** The icon name of a concept, for a design-system attribute that takes one. */
export function iconOf(concept: IconConcept): string {
  return ICONS[concept].icon;
}

/**
 * The attribute a labelled control takes for a concept: the icon before the
 * label, or after it for the concepts that point onward.
 */
export function iconAttribute(concept: IconConcept | undefined): {
  'start-icon'?: string;
  'end-icon'?: string;
} {
  if (!concept) return {};
  const spec: IconSpec = ICONS[concept];
  return spec.position === 'end' ? { 'end-icon': spec.icon } : { 'start-icon': spec.icon };
}

/** The accessible name of an icon-only control: the fixed verb, then what it acts on. */
export function iconLabel(concept: IconConcept, name?: string): string {
  const spec: IconSpec = ICONS[concept];
  const verb = spec.label ?? '';
  return name ? `${verb} ${concept === 'more' ? 'voor ' : ''}${name}`.trim() : verb;
}

/** The one size per context, from the design system's scale. */
export const ICON_SIZE = {
  /** In a line of text or next to a label. */
  inline: '16',
  /** In a table or list cell. */
  cell: '20',
  /** Standing on its own. */
  standalone: '24',
} as const;
