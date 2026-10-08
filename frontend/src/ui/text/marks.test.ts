import { describe, expect, it } from 'vitest';
import {
  QUOTE_SECTION_MARKS,
  VACANCY_SECTION_MARKS,
  VACANCY_TEXT_MARKS,
  openPlaces,
  textBlocks,
  toStored,
} from './marks';

/** Every text grip ships: the standard vacancy texts and the standard texts of a quote. */
const SHIPPED = import.meta.glob<unknown>(
  [
    '../../../../backend/grip/data/vacancy_texts/*.json',
    '../../../../backend/grip/data/profiles/*.json',
  ],
  { eager: true, import: 'default' },
);

/** All strings of a JSON document that read as running text. */
function texts(value: unknown, found: string[] = []): string[] {
  if (typeof value === 'string') {
    if (value.includes(' ') && value.length > 20) found.push(value);
  } else if (Array.isArray(value)) value.forEach((item) => texts(item, found));
  else if (value && typeof value === 'object') Object.values(value).forEach((v) => texts(v, found));
  return found;
}

describe('toStored', () => {
  it('leaves every shipped text exactly as it is stored', () => {
    const all = Object.values(SHIPPED).flatMap((document) => texts(document));
    expect(all.length).toBeGreaterThan(50);
    for (const text of all) {
      expect(toStored(text, QUOTE_SECTION_MARKS)).toBe(text);
      expect(toStored(text, VACANCY_TEXT_MARKS)).toBe(toStored(text, VACANCY_TEXT_MARKS));
    }
    const vacancy = Object.entries(SHIPPED)
      .filter(([file]) => file.includes('vacancy_texts'))
      .flatMap(([, document]) => texts(document));
    expect(vacancy.length).toBeGreaterThan(20);
    for (const text of vacancy) expect(toStored(text, VACANCY_SECTION_MARKS)).toBe(text);
  });

  it('brings what an editor writes back to the marks a quote section knows', () => {
    const typed = [
      '# Te groot',
      '',
      '* een',
      '+ twee',
      '- [ ] drie',
      '',
      '1) eerst',
      '2. dan',
      '',
      '> geciteerd met __nadruk__ en _klem_',
      'Een [link](https://voorbeeld.example) en `code` en ~~weg~~.',
    ].join('\n');
    expect(toStored(typed, QUOTE_SECTION_MARKS)).toBe(
      [
        '### Te groot',
        '',
        '- een',
        '- twee',
        '- drie',
        '',
        '1. eerst',
        '2. dan',
        '',
        'geciteerd met **nadruk** en *klem*',
        'Een link (https://voorbeeld.example) en code en weg.',
      ].join('\n'),
    );
  });

  it('keeps a vacancy text to its own, smaller set', () => {
    expect(toStored('### Kop\n\n1. een\n\n**vet** en *klem*', VACANCY_TEXT_MARKS)).toBe(
      '## Kop\n\n- een\n\n*vet* en *klem*',
    );
    expect(toStored('## Kop\n\ntekst', VACANCY_SECTION_MARKS)).toBe('Kop\n\ntekst');
  });

  it('never touches a passage that is still to fill, or a name between braces', () => {
    const text = 'Je werkt bij {naam_van_het_onderdeel} in [vul aan: het team] aan a_b_c.';
    expect(toStored(text, QUOTE_SECTION_MARKS)).toBe(text);
  });
});

describe('openPlaces', () => {
  it('finds each passage still to fill, with where it stands', () => {
    const text = 'Begin [vul aan: het project] en [vul aan: de taken].';
    const places = openPlaces(text);
    expect(places.map((place) => place.what)).toEqual(['het project', 'de taken']);
    expect(text.slice(places[1]?.start, places[1]?.end)).toBe('[vul aan: de taken]');
    expect(openPlaces('Niets open.')).toEqual([]);
  });
});

describe('textBlocks', () => {
  it('reads headings, paragraphs, lists and emphasis', () => {
    const blocks = textBlocks(
      '## Kop\n\nEen regel\ntweede regel\n\n- een **vet**\n- twee\n\n1. a\n2. b',
    );
    expect(blocks.map((block) => block.kind)).toEqual(['heading', 'paragraph', 'list', 'list']);
    expect(blocks[1]).toMatchObject({
      lines: [[{ text: 'Een regel' }], [{ text: 'tweede regel' }]],
    });
    expect(blocks[2]).toMatchObject({ ordered: false });
    expect(blocks[3]).toMatchObject({ ordered: true });
    const first = blocks[2]?.kind === 'list' ? blocks[2].items[0] : [];
    expect(first).toEqual([{ text: 'een ' }, { text: 'vet', mark: 'strong' }]);
  });
});
