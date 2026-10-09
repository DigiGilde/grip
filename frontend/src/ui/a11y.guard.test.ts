/**
 * The guard of names: what a screen reader needs and a machine can check in
 * the source. This test fails on:
 *
 *   - an icon button without a name (`accessible-label` or `text`);
 *   - an image without an alternative (`alt`, or `aria-hidden` for decoration);
 *   - a native `select` or a design system field without a name of its own
 *     and outside a labelled `nldd-form-field`;
 *   - a table without a name or a caption;
 *   - an empty header cell in a table (the actions column has
 *     `RowActionsHeader`).
 *
 * What a machine cannot see in the source (focus, order, contrast, what a
 * drawing says) is measured in a browser: `just check-a11y` and
 * docs/toegankelijkheid.md.
 */
import { describe, expect, it } from 'vitest';

/** Every source file of the application, as text, keyed by its path from `src`. */
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>('../**/*.tsx', { query: '?raw', import: 'default', eager: true }),
  )
    .map(([file, text]) => [file.replace(/^\.\.\//, '').replace(/^\.\//, 'ui/'), text] as const)
    .filter(([file]) => !/\.(test|d)\.tsx$/.test(file)),
);

function withoutComments(text: string): string {
  return text
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
}

/**
 * The opening tags of an element in a source text, each up to its closing
 * bracket. Braces and quotes are followed, so an arrow function or a
 * comparison in an attribute does not end the tag early.
 */
function openingTags(text: string, tag: string): string[] {
  return openings(text, tag).map((opening) => opening.tag);
}

function openings(text: string, tag: string): { tag: string; before: string; after: string }[] {
  const found: { tag: string; before: string; after: string }[] = [];
  const start = new RegExp(`<${tag}(?=[\\s/>])`, 'g');
  for (let match = start.exec(text); match; match = start.exec(text)) {
    let depth = 0;
    let quote = '';
    let end = match.index;
    for (let i = match.index; i < text.length; i += 1) {
      const char = text[i];
      if (quote) {
        if (char === quote) quote = '';
      } else if (char === '"' || char === "'" || char === '`') quote = char;
      else if (char === '{') depth += 1;
      else if (char === '}') depth -= 1;
      else if (char === '>' && depth === 0) {
        end = i;
        break;
      }
    }
    found.push({
      tag: text.slice(match.index, end + 1),
      before: text.slice(0, match.index),
      after: text.slice(end + 1),
    });
  }
  return found;
}

function hasAttribute(tag: string, names: readonly string[]): boolean {
  // A spread can carry anything; the element that uses one is checked by hand.
  if (/\{\.\.\./.test(tag)) return true;
  return names.some((name) => new RegExp(`[\\s"'}]${name}(=|[\\s/>])`).test(tag));
}

/** Whether the text ends inside an `nldd-form-field` that has a label: it names its control. */
function inLabelledFormField(before: string): boolean {
  const open = before.lastIndexOf('<nldd-form-field');
  if (open < 0 || before.indexOf('</nldd-form-field>', open) >= 0) return false;
  return hasAttribute(openingTags(before.slice(open) + '>', 'nldd-form-field')[0] ?? '', ['label']);
}

interface Named {
  /** A labelled `nldd-form-field` around the element counts as its name. */
  formField?: boolean;
  /** A `caption` as the first child counts as its name. */
  caption?: boolean;
}

/** "file: <tag ...>" for every element of a kind that has none of the names. */
function unnamed(tag: string, names: readonly string[], by: Named = {}): string[] {
  const out: string[] = [];
  for (const [file, raw] of Object.entries(SOURCES)) {
    for (const opening of openings(withoutComments(raw), tag)) {
      if (hasAttribute(opening.tag, names)) continue;
      if (by.formField && inLabelledFormField(opening.before)) continue;
      if (by.caption && /^\s*<caption[\s>]/.test(opening.after)) continue;
      out.push(`${file}: ${opening.tag.replace(/\s+/g, ' ').slice(0, 90)}`);
    }
  }
  return out.sort();
}

describe('names for a screen reader', () => {
  it('every icon button has a name', () => {
    expect(unnamed('nldd-icon-button', ['accessible-label', 'text'])).toEqual([]);
  });

  it('every image has an alternative or is marked as decoration', () => {
    expect(unnamed('img', ['alt', 'aria-hidden'])).toEqual([]);
    expect(unnamed('svg', ['aria-label', 'aria-labelledby', 'aria-hidden', 'role'])).toEqual([]);
  });

  it('every native select has a name', () => {
    expect(unnamed('select', ['aria-label', 'aria-labelledby'], { formField: true })).toEqual([]);
  });

  it('every design system field has a label', () => {
    for (const field of [
      'nldd-text-field',
      'nldd-multi-line-text-field',
      'nldd-date-field',
      'nldd-combo-box',
      'nldd-number-field',
      'nldd-search-field',
      'nldd-text-editor',
      'nldd-file-field',
    ]) {
      expect(unnamed(field, ['accessible-label', 'label'], { formField: true })).toEqual([]);
    }
  });

  it('every table has a name', () => {
    expect(unnamed('nldd-table', ['accessible-label'])).toEqual([]);
    expect(unnamed('table', ['aria-label', 'aria-labelledby'], { caption: true })).toEqual([]);
  });

  it('no header cell of a table is empty', () => {
    const empty: string[] = [];
    for (const [file, raw] of Object.entries(SOURCES)) {
      const text = withoutComments(raw);
      for (const row of text.matchAll(
        /<nldd-table-row slot="header"[^>]*>([\s\S]*?)<\/nldd-table-row>/g,
      )) {
        for (const cell of openingTags(row[1] ?? '', 'nldd-(?:text-)?cell')) {
          if (cell.endsWith('/>') && !hasAttribute(cell, ['text'])) empty.push(`${file}: ${cell}`);
        }
      }
    }
    expect(empty.sort()).toEqual([]);
  });
});
