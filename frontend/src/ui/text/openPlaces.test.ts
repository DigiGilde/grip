import { describe, expect, it } from 'vitest';
import { nextOpenPlace } from './openPlaces';

const TEXT = 'Een [vul aan: a] twee [vul aan: b] drie [vul aan: c].';

describe('nextOpenPlace', () => {
  it('goes to the first place after the caret', () => {
    expect(nextOpenPlace(TEXT, 0)).toEqual({ start: 4, end: 16 });
    expect(nextOpenPlace(TEXT, 5)?.start).toBe(TEXT.indexOf('[vul aan: b]'));
  });

  it('does not skip a place after one was filled', () => {
    // The first place was replaced by typed text; the caret stands behind it.
    const filled = TEXT.replace('[vul aan: a]', 'ingevuld');
    const caret = filled.indexOf('ingevuld') + 'ingevuld'.length;
    expect(nextOpenPlace(filled, caret)?.start).toBe(filled.indexOf('[vul aan: b]'));
  });

  it('starts again at the top after the last, and knows when none is left', () => {
    expect(nextOpenPlace(TEXT, TEXT.length)?.start).toBe(4);
    expect(nextOpenPlace('Niets open.', 0)).toBeNull();
  });
});
