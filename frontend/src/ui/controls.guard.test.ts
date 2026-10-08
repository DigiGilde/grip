/**
 * The guard of buttons and text fields.
 *
 * Buttons have three ranks (`@/ui/Button`); an action is never bare text.
 * Text is typed in the design system's own inputs through one wrapper per
 * kind (`@/ui/fields`, `@/ui/TextEditor`). This test fails on:
 *
 *   - the bare-text button style outside the foundation;
 *   - `QuietButton` outside the places it is for (the way out of a form, a
 *     small action inside a line of a conversation);
 *   - a raw textarea, text input or contenteditable in feature code;
 *   - a design system text field used directly instead of through a wrapper.
 *
 * Each list of known exceptions may only shrink: an entry that no longer
 * breaks the rule fails the test until it is removed.
 */
import { describe, expect, it } from 'vitest';

/** Every source file of the application, as text, keyed by its path from `src`. */
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }),
  )
    .map(([file, text]) => [file.replace(/^\.\.\//, '').replace(/^\.\//, 'ui/'), text] as const)
    .filter(([file]) => !/\.(test|d)\.tsx?$/.test(file)),
);

function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

function filesWith(pattern: RegExp, allowed: readonly string[]): string[] {
  return Object.entries(SOURCES)
    .filter(([file]) => !allowed.some((prefix) => file.startsWith(prefix)))
    .filter(([, raw]) => pattern.test(withoutComments(raw)))
    .map(([file]) => file)
    .sort();
}

function expectOnly(found: string[], known: readonly string[]) {
  expect(found.filter((file) => !known.includes(file))).toEqual([]);
  expect(known.filter((file) => !found.includes(file))).toEqual([]);
}

describe('buttons', () => {
  it('are never bare text outside the foundation', () => {
    const found = filesWith(/neutral-transparent/, ['ui/Button.tsx']);
    expectOnly(found, [
      // The account button in the bar opens a menu; the bar has its own style.
      'layout/AccountMenu.tsx',
      // "Annuleer" of a form in a section: mapped onto QuietButton.
      'features/team/ui/actions.ts',
      'features/team/ui/controls.tsx',
      // Owned by work in flight on the history feed.
      'features/history/History.tsx',
      // An icon button without text has no box by design.
      'ui/Icon.tsx',
    ]);
  });

  it('are quiet only as the way out of a form or inside a line of a conversation', () => {
    const found = filesWith(/<QuietButton\b/, ['ui/Button.tsx']);
    expectOnly(found, [
      'features/team/ui/controls.tsx',
      // Answering a remark and marking it handled, under that remark.
      'features/vacancies/TextWork.tsx',
    ]);
  });
});

describe('text fields', () => {
  it('are never a raw textarea, input or contenteditable', () => {
    const found = filesWith(/<textarea\b|<input\b|contentEditable|contenteditable/, []);
    expectOnly(found, []);
  });

  it('go through one wrapper per kind', () => {
    const found = filesWith(/<nldd-(?:multi-line-text-field|text-field|text-editor)\b/, [
      'ui/fields.tsx',
      'ui/TextEditor.tsx',
    ]);
    expectOnly(found, [
      // A field inside a row or a picker that lays out its own label.
      'features/costs/CostSheets.tsx',
      'features/month-close/MonthSheet.tsx',
      'features/organisations/OrganisationPicker.tsx',
    ]);
  });
});
