import { describe, expect, it } from 'vitest';
import { factPlaces, nextPlaceToFill, placesToFill, unknownFacts, withFacts } from './facts';
import type { TextFact } from './facts';
import { VACANCY_TEXT_MARKS, toStored } from './marks';

const fact = (key: string, value: string | null, instruction = `Vul ${key} in`): TextFact => ({
  key,
  label: key,
  value,
  source: `uit de aanvraag: ${key}`,
  where: 'request',
  instruction,
});

const FACTS = [
  fact('schaal', '12'),
  fact('contract', null, 'Kies het soort contract op de aanvraag'),
];
const TEXT = [
  '## Dit bieden wij',
  '',
  '- Salaris in schaal {schaal}, volgens de cao Rijk',
  '- {contract}',
  '',
  'Wij zijn [vul aan: beschrijf wat het team maakt]. Zie {onbekend}.',
].join('\n');

describe('facts in a text', () => {
  it('finds the places that name a known key and leaves other braces alone', () => {
    expect(factPlaces(TEXT, FACTS).map((place) => place.fact.key)).toEqual(['schaal', 'contract']);
  });

  it('reads with the value, and with where to fill it when the value is unknown', () => {
    const shown = withFacts(TEXT, FACTS);
    expect(shown).toContain('- Salaris in schaal 12, volgens de cao Rijk');
    expect(shown).toContain('- [vul aan: Kies het soort contract op de aanvraag]');
    expect(shown).toContain('Zie {onbekend}.');
  });

  it('names an unknown fact once', () => {
    expect(unknownFacts(`${TEXT}\n{contract}`, FACTS).map((item) => item.key)).toEqual([
      'contract',
    ]);
  });

  it('walks prose places and unknown facts, never a fact that is known', () => {
    const places = placesToFill(TEXT, FACTS);
    expect(places.map((place) => place.kind)).toEqual(['fact', 'prose']);
    expect(places[1]?.what).toBe('beschrijf wat het team maakt');
    const first = nextPlaceToFill(TEXT, FACTS, 0);
    expect(first?.text).toBe('{contract}');
    const second = nextPlaceToFill(TEXT, FACTS, first?.end ?? 0);
    expect(second?.text).toBe('[vul aan: beschrijf wat het team maakt]');
    // Past the last one it starts again at the top.
    expect(nextPlaceToFill(TEXT, FACTS, TEXT.length)?.text).toBe('{contract}');
  });

  it('keeps the keys and what a person typed when the text is stored', () => {
    const typed = `${TEXT}\n\nEen eigen zin met **nadruk** en {schaal}.`;
    const stored = toStored(typed, VACANCY_TEXT_MARKS);
    expect(stored).toContain('- Salaris in schaal {schaal}, volgens de cao Rijk');
    expect(stored).toContain('Een eigen zin met *nadruk* en {schaal}.');
    expect(toStored(stored, VACANCY_TEXT_MARKS)).toBe(stored);
  });
});
