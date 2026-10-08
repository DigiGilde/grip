import { describe, expect, it } from 'vitest';
import { mismatchText } from '@/features/allocations/board/model';
import { bar } from '@/features/allocations/board/testing';
import { cardOn, categoryDiffers, categoryOptionText, categoryText } from './rateText';

const plain = (text: string) => text.replace(/\u00a0|\u202f/g, ' ');

const card = (year: number, rateB: number, status = 'active', validTo: string | null = `${year}-12-31`) => ({
  status: status as 'active',
  valid_from: `${year}-01-01`,
  valid_to: validTo,
  rate_bands: [
    { category: 'B', monthly_rate_cents: rateB },
    { category: 'C', monthly_rate_cents: 1500000 },
  ],
  scale_bands: [
    { scale: 11, category: 'B' },
    { scale: 10, category: 'B' },
    { scale: 12, category: 'C' },
  ],
});

describe('a rate category in words', () => {
  it('leads with the scales, then the letter, then the monthly rate', () => {
    expect(plain(categoryOptionText(card(2026, 1312500), 'B'))).toBe(
      'Schaal 10 en 11 (categorie B), € 13.125 per maand',
    );
    expect(categoryText(card(2026, 1312500), 'C')).toBe('Schaal 12 (categorie C)');
  });

  it('falls back to the letter without a card that maps it', () => {
    expect(categoryText(null, 'D')).toBe('Categorie D');
    expect(categoryText(card(2026, 1), 'E')).toBe('Categorie E');
  });

  it('prices a day with the card valid then, and never with a draft', () => {
    const half = { ...card(2026, 1312500), valid_to: '2026-06-30' };
    const rest = { ...card(2026, 1400000, 'active', null), valid_from: '2026-07-01' };
    const cards = [half, rest, card(2028, 1378100, 'draft')];
    expect(cardOn(cards, '2026-03-15')).toBe(half);
    expect(cardOn(cards, '2026-07-01')).toBe(rest);
    // An open-ended card keeps pricing; a draft never does.
    expect(cardOn(cards, '2027-02-01')).toBe(rest);
    expect(cardOn([card(2028, 1, 'draft')], '2028-02-01')).toBeNull();
  });

  it('notices when two years differ for a category', () => {
    expect(categoryDiffers(card(2026, 1312500), card(2027, 1378100), 'B')).toBe(true);
    expect(categoryDiffers(card(2026, 1312500), card(2027, 1378100), 'C')).toBe(false);
  });

  it('adds the scales to the R14 message for a reader who got the categories', () => {
    const name = (category: string) => categoryText(card(2026, 1), category);
    const text = mismatchText(
      bar({ category_mismatch: true, person_category: 'C', line_category: 'B' }),
      name,
    );
    expect(text).toBe(
      'declareert in schaal 12 (categorie C), de regel rekent met schaal 10 en 11 (categorie B)',
    );
    expect(mismatchText(bar({ category_mismatch: true }), name)).not.toMatch(/schaal/i);
  });
});
