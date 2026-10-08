/**
 * The guard of the icon vocabulary.
 *
 * An icon name is written in one place, `@/ui/icons`. Everywhere else code
 * names a concept. This test fails on a raw icon name, a raw icon element or
 * a symbol character used as an icon outside the foundation, and on a
 * vocabulary entry that the design system does not have.
 *
 * `KNOWN` lists the files that still break the rule, each owned by work that
 * was in flight when the vocabulary landed. The list may only shrink: a file
 * on it that no longer breaks the rule fails the test until it is removed.
 */
import { describe, expect, it } from 'vitest';
import aliases from '../../node_modules/@nldd/design-system/dist/components/content/icon/icon-aliases.js?raw';
import registry from '../../node_modules/@nldd/design-system/dist/components/content/icon/icon-registry.js?raw';
import { ICONS } from './icons';

/** Every source file of the application, as text, keyed by its path from `src`. */
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }),
  )
    .map(([file, text]) => [file.replace(/^\.\.\//, '').replace(/^\.\//, 'ui/'), text] as const)
    .filter(([file]) => !/\.(test|d)\.tsx?$/.test(file)),
);

/** Where an icon name or element may be written. */
const FOUNDATION = ['ui/icons.ts', 'ui/Icon.tsx', 'components/nldd/'];

/** Files that still write icons by hand; convert them and remove them here. */
const KNOWN: readonly string[] = [
  'features/assignments/staffingModel.ts',
  'features/assignments/tabs/FinanceTab.tsx',
  'features/allocations/board/model.ts',
  'features/form-templates/FormTemplatePage.tsx',
  'features/reports/occupancy/Heatmap.tsx',
  'features/vacancies/tabs/VacancyTabs.tsx',
  'layout/AccountMenu.tsx',
  'layout/DevPersonSwitch.tsx',
  'layout/MainNavigation.tsx',
  'pages/AdminPage.tsx',
  'routes.ts',
  'ui/timeline/Timeline.tsx',
];

const RAW_ICON_NAME = /\b(?:start-icon|end-icon|icon)\s*[=:]\s*\{?\s*["'`][a-z0-9-]+["'`]/;
const RAW_ICON_ELEMENT = /<nldd-icon(?:-cell|-button)?\b/;
// Arrows, check marks, crosses and the like in a string or in JSX text: an
// icon in disguise. The multiplication sign and the ellipsis are text.
const SYMBOL = /[←→↑↓✓✔✕✗≠›‹»«▸▾▴]|mark:\s*'!'|>!<|'! '/;

function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

function offenders(): string[] {
  return Object.entries(SOURCES)
    .filter(([file]) => !FOUNDATION.some((allowed) => file.startsWith(allowed)))
    .filter(([, raw]) => {
      const text = withoutComments(raw);
      return RAW_ICON_NAME.test(text) || RAW_ICON_ELEMENT.test(text) || SYMBOL.test(text);
    })
    .map(([file]) => file)
    .sort();
}

describe('icon vocabulary', () => {
  it('is the only place an icon is named', () => {
    const found = offenders();
    expect(found.filter((file) => !KNOWN.includes(file))).toEqual([]);
  });

  it('keeps no exception that is no longer needed', () => {
    const found = offenders();
    expect(KNOWN.filter((file) => !found.includes(file))).toEqual([]);
  });

  it('uses only icons the design system has', () => {
    const missing = Object.values(ICONS)
      .map((spec) => spec.icon)
      .filter((name) => !registry.includes(`['${name}',`) && !aliases.includes(`'${name}':`));
    expect(missing).toEqual([]);
  });

  it('gives one concept one icon and one icon one concept', () => {
    const byIcon = new Map<string, string[]>();
    for (const [concept, spec] of Object.entries(ICONS)) {
      byIcon.set(spec.icon, [...(byIcon.get(spec.icon) ?? []), concept]);
    }
    expect([...byIcon.entries()].filter(([, concepts]) => concepts.length > 1)).toEqual([]);
  });

  it('names every concept that can stand alone', () => {
    const standalone = [
      'more',
      'add',
      'remove',
      'download',
      'upload',
      'back',
      'elsewhere',
      'open',
      'close',
      'copy',
      'search',
      'undo',
      'done',
      'todo',
      'waiting',
      'attention',
      'error',
      'info',
      'locked',
      'account',
      'menu',
    ] as const;
    expect(standalone.filter((concept) => !('label' in ICONS[concept]))).toEqual([]);
  });
});
