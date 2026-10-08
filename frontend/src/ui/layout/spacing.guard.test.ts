/**
 * Guards the one spacing scale (docs/ontwerp.md).
 *
 * Two mistakes put a page off the scale: a `gap` on a container that is not a
 * step of the scale, and a margin, padding or gap in pixels in feature code.
 * Both fail here. What exists today is listed as an exception with its count,
 * so the list can only shrink: lower a number when you remove one, and never
 * add a file. The measure in a browser (`just check-spacing`) finds what a
 * reading of the source cannot.
 */
import { describe, expect, it } from 'vitest';

/** Every source file of the application, as text, keyed by its path from `src`. */
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>('../../**/*.{ts,tsx,css}', {
      query: '?raw',
      import: 'default',
      eager: true,
    }),
  )
    .map(
      ([file, text]) =>
        [file.replace(/^(\.\.\/)+/, '').replace(/^\.\//, 'ui/layout/'), text] as const,
    )
    .filter(([file]) => !/\.(test|d)\.tsx?$/.test(file)),
);

/** The scale, plus 20 between form fields and 32 under a page title. */
const SCALE = new Set(['0', '4', '8', '16', '20', '24', '32', '48']);

/** Containers with a gap off the scale, per file. Owned by other work in progress. */
const GAP_EXCEPTIONS: Record<string, number> = {};

/**
 * Spacing in pixels (or rem) per file. A drawn figure (a chart, a timeline, a
 * path) sets its own geometry; a page or a form never does.
 */
const PIXEL_EXCEPTIONS: Record<string, number> = {
  'features/costs/costs.css': 11,
  'features/nodes/path.css': 7,
  'features/overview/overview.css': 1,
  'features/reports/charts/MonthColumns.tsx': 2,
  'features/reports/reports.css': 41,
  'index.css': 3,
  'layout/shell.css': 3,
  'ui/timeline/timeline.css': 20,
};

function count(pattern: RegExp, accept: (match: RegExpMatchArray) => boolean = () => true) {
  const found: Record<string, number> = {};
  for (const [file, text] of Object.entries(SOURCES)) {
    const hits = [...text.matchAll(pattern)].filter(accept).length;
    if (hits > 0) found[file] = hits;
  }
  return found;
}

/** No file beyond the listed ones, and no listed file with more than it had. */
function expectWithin(found: Record<string, number>, allowed: Record<string, number>) {
  const over = Object.entries(found)
    .filter(([file, hits]) => hits > (allowed[file] ?? 0))
    .map(([file, hits]) => `${file}: ${hits} (toegestaan ${allowed[file] ?? 0})`);
  expect(over).toEqual([]);
}

describe('spacing scale', () => {
  it('uses only steps of the scale as a gap', () => {
    const found = count(/\bgap="(\d+)"/g, (match) => !SCALE.has(match[1] ?? ''));
    expectWithin(found, GAP_EXCEPTIONS);
  });

  it('writes no margin, padding or gap in pixels outside the listed drawings', () => {
    const found = count(
      /(margin|padding|gap|inset|top|left)[a-zA-Z-]*:\s*[^;]*[0-9.]+(px|rem|em)/g,
    );
    expectWithin(found, PIXEL_EXCEPTIONS);
  });
});
