import { describe, expect, it } from 'vitest';
import type { Sender, TextBlock } from './api';
import { blockKind, contactLine, fromLines, keyFromHeading, moved, toLines } from './text';

const block = (over: Partial<TextBlock>): TextBlock => ({
  key: 'a',
  heading: 'A',
  body: '',
  hint: '',
  included: true,
  with_costs: false,
  numbered: true,
  draftable: false,
  required: false,
  ...over,
});

describe('quote letter text helpers', () => {
  it('turns a field into lines and back, without empty lines', () => {
    expect(toLines(' Voorbeeldlaan 1 \n\n1234 AB Voorbeeldstad\n')).toEqual([
      'Voorbeeldlaan 1',
      '1234 AB Voorbeeldstad',
    ]);
    expect(fromLines(['a', 'b'])).toBe('a\nb');
  });

  it('says what a block is', () => {
    expect(blockKind(block({ with_costs: true }))).toBe('Bedragen uit de begroting');
    expect(blockKind(block({ body: 'Tekst.' }))).toBe('Standaardtekst');
    expect(blockKind(block({ draftable: true }))).toBe('Schrijf je per offerte, concept mogelijk');
    expect(blockKind(block({}))).toBe('Schrijf je per offerte');
  });

  it('makes a key from a heading that is not taken yet', () => {
    expect(keyFromHeading('Beoogde resultaten', [])).toBe('beoogde-resultaten');
    expect(keyFromHeading('Coördinatie', ['coordinatie'])).toBe('coordinatie-2');
    expect(keyFromHeading('!!!', [])).toBe('onderdeel');
  });

  it('moves an item one place and stays inside the list', () => {
    expect(moved(['a', 'b', 'c'], 1, -1)).toEqual(['b', 'a', 'c']);
    expect(moved(['a', 'b', 'c'], 2, 1)).toEqual(['a', 'b', 'c']);
  });

  it('writes the contact person as one line', () => {
    const sender = {
      contact: {
        name: 'Vera Voorbeeld',
        role: 'Businessmanager',
        email: 'v@voorbeeld.example',
        phone: '',
      },
    } as Sender;
    expect(contactLine(sender)).toBe('Vera Voorbeeld (Businessmanager), v@voorbeeld.example');
  });
});
