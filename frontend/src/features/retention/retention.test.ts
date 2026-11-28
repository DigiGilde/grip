import { describe, expect, it } from 'vitest';
import {
  caseRuleOf,
  caseRuleText,
  choiceOf,
  closeAfterProposalText,
  eventsText,
  inputOf,
  MAX_DAYS,
  proposeCloseText,
  requestFormsText,
  wholeNumber,
} from './retention';

describe('the rule for an assignment', () => {
  it('reads what the server holds', () => {
    expect(caseRuleOf(null)).toBeNull();
    expect(caseRuleOf({ outcome: 'keep' })).toEqual({ outcome: 'keep' });
    expect(caseRuleOf({ outcome: 'destroy', years: 7 })).toEqual({ outcome: 'destroy', years: 7 });
    expect(caseRuleOf({ outcome: 'destroy' })).toBeNull();
    expect(caseRuleOf('keep')).toBeNull();
  });

  it('says it in plain words', () => {
    expect(caseRuleText({ outcome: 'destroy', years: 7 })).toBe('Vernietigen na 7 jaar');
    expect(caseRuleText({ outcome: 'destroy', years: 1 })).toBe('Vernietigen na 1 jaar');
    expect(caseRuleText({ outcome: 'keep' })).toBe('Blijvend bewaren');
    expect(caseRuleText(null)).toBe('Nog niet bepaald: niets wordt vernietigd');
  });

  it('opens the form on the choice that stands', () => {
    expect(choiceOf(null)).toBe('none');
    expect(choiceOf({ outcome: 'keep' })).toBe('keep');
    expect(choiceOf({ outcome: 'destroy', years: 3 })).toBe('destroy');
  });
});

describe('the periods per kind of data', () => {
  it('reads zero as never for the stream', () => {
    expect(eventsText(0)).toBe('Nooit gewist');
    expect(eventsText(1)).toBe('Gewist na 1 dag');
    expect(eventsText(365)).toBe('Gewist na 365 dagen');
  });

  it('reads zero as the next round for the request forms', () => {
    expect(requestFormsText(0)).toBe(
      'Verwijderd bij de eerstvolgende nachtelijke ronde nadat de vacature is vervuld, ingetrokken of afgewezen',
    );
    expect(requestFormsText(30)).toBe(
      'Verwijderd 30 dagen nadat de vacature is vervuld, ingetrokken of afgewezen',
    );
  });
});

describe('closing a dossier', () => {
  it('reads empty as never', () => {
    expect(proposeCloseText(null)).toBe('Nooit');
    expect(proposeCloseText(365)).toBe('Na 365 dagen zonder wijziging');
    expect(closeAfterProposalText(null)).toBe('Nooit');
    expect(closeAfterProposalText(90)).toBe('90 dagen na die taak');
  });
});

describe('a typed number', () => {
  it('takes a whole number within the bounds', () => {
    expect(wholeNumber('7', 1, 100)).toBe(7);
    expect(wholeNumber(' 100 ', 1, 100)).toBe(100);
    expect(wholeNumber('0', 0)).toBe(0);
    expect(wholeNumber('36500', 0, MAX_DAYS)).toBe(36500);
  });

  it('refuses anything else', () => {
    for (const input of ['', ' ', '0', '101', '-1', '7.5', '7,5', 'zeven', '1e2', '٣']) {
      expect(wholeNumber(input, 1, 100)).toBeNull();
    }
  });

  it('keeps a term in days on the calendar', () => {
    for (const input of ['36501', '1000000', '99999999999999999999']) {
      expect(wholeNumber(input, 0, MAX_DAYS)).toBeNull();
    }
  });

  it('puts a stored number back in the field', () => {
    expect(inputOf(30)).toBe('30');
    expect(inputOf(null)).toBe('');
  });
});
