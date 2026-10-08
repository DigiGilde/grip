import { describe, expect, it } from 'vitest';
import { courseAction, courseBrief, courseLine, type Course } from './course';

const base: Course = {
  key: 'akkoord',
  label: 'Naar een akkoord',
  steps: [],
  current_label: 'Aanbieden',
};

describe('what a list and a head say of a course', () => {
  it('names the step and the move of the reader', () => {
    const course: Course = {
      ...base,
      next: {
        mine: true,
        headline: 'Bied de offerte aan',
        sentence: 'De offerte is gemaakt. Bied haar aan.',
        action_text: 'Bied de offerte aan',
        action_href: '/opdrachten/a1/offerte',
      },
    };
    expect(courseLine(course)).toEqual({
      step: 'Aanbieden',
      who: 'Jij: bied de offerte aan',
      mine: true,
      overdue: false,
    });
    expect(courseAction(course)).toEqual({
      text: 'Bied de offerte aan',
      href: '/opdrachten/a1/offerte',
    });
  });

  it('says who is waited on and offers no action to who waits', () => {
    const course: Course = {
      ...base,
      current_label: 'Akkoord',
      next: { mine: false, headline: 'Akkoord', sentence: '', who: 'Voorbeeldministerie' },
    };
    expect(courseLine(course)?.who).toBe('Wacht op Voorbeeldministerie');
    expect(courseAction(course)).toBeNull();
  });

  it('says how a case ended, and nothing of a move', () => {
    expect(courseLine({ ...base, ended: 'Ingetrokken', next: null })).toEqual({
      step: 'Ingetrokken',
      who: '',
      mine: false,
      overdue: false,
    });
  });

  it('says nothing without a course', () => {
    expect(courseLine(null)).toBeNull();
    expect(courseAction(undefined)).toBeNull();
  });
});

describe('a reader with no part in the step', () => {
  it('is told whose move it is, never that they wait', () => {
    const course: Course = {
      ...base,
      current_label: 'Uitvoeren',
      next: {
        mine: false,
        part: 'watches',
        headline: 'De afsluiting van maart 2026',
        sentence: 'De eigenaar is aan zet: de afsluiting van maart 2026.',
        who: 'de eigenaar',
      },
    };
    expect(courseLine(course)).toEqual({
      step: 'Uitvoeren',
      who: 'de eigenaar is aan zet',
      mine: false,
      overdue: false,
    });
    expect(courseAction(course)).toBeNull();
  });
});

describe('the course in words, for a narrow screen', () => {
  const steps = (states: ('done' | 'current' | 'future')[]): Course => ({
    ...base,
    steps: ['Begroting', 'Offerte', 'Aanbieden', 'Akkoord'].map((label, index) => ({
      key: label,
      label,
      state: states[index] ?? 'future',
    })),
  });

  it('names the step it is at and the one after', () => {
    expect(courseBrief(steps(['done', 'current', 'future', 'future']))).toEqual({
      now: 'Offerte',
      then: 'daarna aanbieden',
    });
  });

  it('skips a later step that was already done', () => {
    expect(courseBrief(steps(['done', 'current', 'done', 'future']))?.then).toBe('daarna akkoord');
  });

  it('says so at the last step, and nothing once all is done', () => {
    expect(courseBrief(steps(['done', 'done', 'done', 'current']))?.then).toBe('de laatste stap');
    expect(courseBrief(steps(['done', 'done', 'done', 'done']))).toBeNull();
  });
});
