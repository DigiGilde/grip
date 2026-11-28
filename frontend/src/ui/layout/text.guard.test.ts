/**
 * Guards the one text color (docs/ontwerp.md).
 *
 * All text we write is the normal text color; what matters less is smaller
 * (`Quiet`), not grey. Grey is only what the design system draws itself: a
 * supporting text, a placeholder, a disabled state. This test fails on a grey
 * color on our own text, in markup and in our stylesheets. A color with a
 * meaning (critical, warning) is not grey and passes.
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
    .map(([file, text]) => [file.replace(/^\.\.\/\.\.\//, ''), text] as const)
    .filter(([file]) => !/\.(test|d)\.tsx?$/.test(file)),
);

function filesWith(extension: RegExp, pattern: RegExp): string[] {
  return Object.entries(SOURCES)
    .filter(([file, text]) => extension.test(file) && pattern.test(text))
    .map(([file]) => file)
    .sort();
}

describe('text color', () => {
  it('is never secondary on text in markup', () => {
    expect(filesWith(/\.tsx$/, /color="secondary"|color:\s*'secondary'/)).toEqual([]);
  });

  it('is never a grey in our stylesheets', () => {
    const grey =
      /(^|[^-])color:\s*var\(--(semantics-content-secondary-color|primitives-color-neutral-[4-7]\d\d)\)/m;
    expect(filesWith(/\.css$/, grey)).toEqual([]);
  });
});
