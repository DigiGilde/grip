import { describe, expect, it } from 'vitest';
import { courseAction, courseLine, type Course } from './course';

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
