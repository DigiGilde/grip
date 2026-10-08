import { describe, expect, it } from 'vitest';
import { documentTitle, instanceNames } from './names';

describe('instanceNames', () => {
  it('takes the product and the environment note off the organisation', () => {
    expect(instanceNames('Grip Voorbeeldgilde (voorbeeld)')).toEqual({
      organisation: 'Voorbeeldgilde',
      environment: 'voorbeeld',
    });
  });

  it('leaves a plain organisation name alone', () => {
    expect(instanceNames('Voorbeelddienst Uitvoering')).toEqual({
      organisation: 'Voorbeelddienst Uitvoering',
    });
  });

  it('keeps a name that only starts with the same letters', () => {
    expect(instanceNames('Gripvast Advies')).toEqual({ organisation: 'Gripvast Advies' });
  });

  it('has no organisation while the instance is unknown', () => {
    expect(instanceNames(undefined)).toEqual({ organisation: '' });
    expect(instanceNames('Grip')).toEqual({ organisation: '' });
  });
});

describe('documentTitle', () => {
  it('puts the page first, then the organisation, then the product', () => {
    expect(documentTitle('Taken', 'Grip Voorbeeldgilde (voorbeeld)')).toBe(
      'Taken · Voorbeeldgilde · grip',
    );
  });

  it('names only the product while the instance is unknown', () => {
    expect(documentTitle('Inloggen')).toBe('Inloggen · grip');
  });
});
