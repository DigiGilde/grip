/**
 * The guard of the word "Gerealiseerd".
 *
 * `realised_cents` is the inzet of closed months and is called "Gerealiseerde
 * inzet". "Gerealiseerd" is `realised_total_cents`: that inzet plus the
 * realised costs. This test fails on the word "Gerealiseerd" in the lines
 * around a `realised_cents`. The realised part of a cost (`costs_realised_cents`,
 * `cost.realised_cents`) is the same notion as the word and may use it.
 */
import { describe, expect, it } from 'vitest';

const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }),
  )
    .map(([file, text]) => [file.replace(/^\.\.\//, ''), text] as const)
    .filter(([file]) => !/\.(test|d)\.tsx?$/.test(file) && !/(^|\/)testing\.tsx?$/.test(file)),
);

const WORD = /gerealiseerd(?!e)/i;
const EFFORT_FIELD = /(?<!costs_)(?<!cost\.)realised_cents/;
const REACH = 2;

function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

function offenders(sources: Record<string, string>): string[] {
  const found: string[] = [];
  for (const [file, text] of Object.entries(sources)) {
    const lines = withoutComments(text).split('\n');
    lines.forEach((line, index) => {
      if (!WORD.test(line)) return;
      const around = lines.slice(Math.max(0, index - REACH), index + REACH + 1).join('\n');
      if (EFFORT_FIELD.test(around)) found.push(`${file}:${index + 1}: ${line.trim()}`);
    });
  }
  return found;
}

describe('the word Gerealiseerd', () => {
  it('does not stand next to realised_cents in the application', () => {
    expect(offenders(SOURCES)).toEqual([]);
  });

  it('catches the word next to the inzet field and leaves the total and the costs alone', () => {
    const wrong = `<nldd-text-cell text="Gerealiseerd" />\n<MoneyCell cents={totals.realised_cents} />`;
    const total = `label: 'Gerealiseerd',\nvalue: euros(figures.realised_total_cents),`;
    const costs = '`${formatEuro(cost.realised_cents)} gerealiseerd`';
    const inzet = `label: 'Gerealiseerde inzet',\nvalue: euros(totals.realised_cents),`;
    expect(offenders({ wrong })).toHaveLength(1);
    expect(offenders({ total, costs, inzet })).toEqual([]);
  });
});
