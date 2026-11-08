/**
 * The guard of the old words. The screen says Potentieel, Start, Team and
 * Geschiedenis; Pijplijn, Bemensing, Stand van zaken, Spoor and a part titled
 * "Wat er gebeurd is" are gone. Keys of data (`pipeline_*`, routes) are not
 * screen text and are not read here.
 */
import { describe, expect, it } from 'vitest';

const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }),
  )
    .map(([file, text]) => [file.replace(/^\.\.\//, ''), text] as const)
    .filter(([file]) => !/\.(test|d)\.tsx?$/.test(file) && !/(^|\/)testing\.tsx?$/.test(file)),
);

const OLD_WORDS: RegExp[] = [
  /pijplijn/i,
  /bemensing/i,
  /stand van zaken/i,
  /(title|label|text|heading)\s*[=:]\s*\{?\s*['"`]Wat er gebeurd is/i,
  // The filter and the standings say "soort werk"; a key like 'spoor' alone is data.
  /(["'`])(?!spoor\1)[^"'`\n]*\b([Ss]poor|[Ss]poren)\b[^"'`\n]*\1/,
];

function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

function offenders(sources: Record<string, string>): string[] {
  const found: string[] = [];
  for (const [file, text] of Object.entries(sources)) {
    withoutComments(text)
      .split('\n')
      .forEach((line, index) => {
        if (OLD_WORDS.some((word) => word.test(line))) {
          found.push(`${file}:${index + 1}: ${line.trim()}`);
        }
      });
  }
  return found;
}

describe('the old words', () => {
  it('do not stand in the text of the application', () => {
    expect(offenders(SOURCES)).toEqual([]);
  });

  it('fail on each of the old words', () => {
    expect(offenders({ a: `<nldd-title text="Pijplijn" />` })).toHaveLength(1);
    expect(offenders({ a: `const label = 'Bemensing van de opdracht';` })).toHaveLength(1);
    expect(offenders({ a: `<Section title="Stand van zaken" />` })).toHaveLength(1);
    expect(offenders({ a: `{ key: 'log', text: 'Wat er gebeurd is' }` })).toHaveLength(1);
    expect(offenders({ a: `{ label: 'Spoor', onChange: set('spoor') }` })).toHaveLength(1);
    expect(offenders({ a: `options: optionsOf(all, pick, 'Alle sporen')` })).toHaveLength(1);
  });

  it('leaves a keyed field, a comment and a link to everything that happened alone', () => {
    expect(offenders({ a: `const total = row.pipeline_cents;` })).toEqual([]);
    expect(offenders({ a: `track: params.get('spoor') ?? ALL` })).toEqual([]);
    expect(offenders({ a: `// the Pijplijn was renamed` })).toEqual([]);
    expect(offenders({ a: `{ key: 'all', text: 'Alles wat er gebeurd is' }` })).toEqual([]);
  });
});
