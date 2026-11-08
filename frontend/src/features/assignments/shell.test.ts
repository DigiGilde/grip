import { describe, expect, it } from 'vitest';
import type { Task } from '@/features/tasks/api';
import type { Course } from '@/ui/course';
import { stepOnPart, withOwnTask } from './shell';
import { assignment } from './testing';
import { daysSince, durationText, phaseOfView, viewHref } from './views';
import { assignmentInput, initialState } from './assignmentForm';

describe('stepOnPart', () => {
  const step = (href: string): Course => ({
    key: 'k',
    label: 'l',
    steps: [],
    next: {
      mine: true,
      headline: 'h',
      sentence: 's',
      action_text: 'Sluit maart af',
      action_href: href,
    },
  });

  it('stands in the head of the part it leads to when the address opens something', () => {
    const course = step('/opdrachten/a1/afsluiten?maand=2026-03');
    expect(stepOnPart(course, 'a1', 'close')).toEqual({
      text: 'Sluit maart af',
      href: '/opdrachten/a1/afsluiten?maand=2026-03',
    });
    expect(stepOnPart(course, 'a1', 'team')).toBeNull();
  });

  it('leaves a step that only names the part to the button of the part', () => {
    expect(stepOnPart(step('/opdrachten/a1/offerte'), 'a1', 'quote')).toBeNull();
  });

  it('has nothing for who is not at move', () => {
    const course = step('/opdrachten/a1/afsluiten?maand=2026-03');
    expect(
      stepOnPart({ ...course, next: { ...course.next!, mine: false } }, 'a1', 'close'),
    ).toBeNull();
    expect(stepOnPart(null, 'a1', 'close')).toBeNull();
  });
});

describe('withOwnTask', () => {
  const waits: Course = {
    key: 'k',
    label: 'l',
    steps: [],
    next: {
      mine: false,
      part: 'waits',
      headline: 'Het aanbieden van de offerte',
      sentence: 'Je wacht op Lotte Leiding. Jij hoeft nu niets te doen.',
      may_take_over: true,
    },
  };
  const task = (id: string, needs_me: boolean) =>
    ({
      id,
      title: 'Vul de rol in',
      headline: 'Vul de rol Developer in',
      instruction: 'Plan iemand in, of open een vacature.',
      action_text: 'Vul de rol in',
      work_href: '/opdrachten/a1/team',
      needs_me,
    }) as Task;

  it('never tells someone to wait while a task of their own lies elsewhere in the case', () => {
    const told = withOwnTask(waits, [
      { tasks: [task('t0', false)] },
      { tasks: [task('t1', true), task('t2', true)] },
    ]);
    expect(told?.next?.mine).toBe(true);
    expect(told?.next?.sentence).toBe('Plan iemand in, of open een vacature.');
    expect(told?.next?.action_href).toBe('/opdrachten/a1/team');
    expect(told?.next?.may_take_over).toBeUndefined();
    expect(told?.more_to_do).toBe(1);
  });

  it('leaves the course as it is without such a task, or when the reader is at move', () => {
    expect(withOwnTask(waits, [{ tasks: [task('t0', false)] }])).toBe(waits);
    const mine = { ...waits, next: { ...waits.next!, mine: true } };
    expect(withOwnTask(mine, [{ tasks: [task('t1', true)] }])).toBe(mine);
    expect(withOwnTask(null, [{ tasks: [task('t1', true)] }])).toBeNull();
  });

  it('asks nothing of a case that has ended', () => {
    const ended = { ...waits, ended: 'Afgewezen' };
    expect(withOwnTask(ended, [{ tasks: [task('t1', true)] }])).toBe(ended);
  });
});

describe('list views', () => {
  it('shows running work by default and reads the view from the address', () => {
    expect(phaseOfView(null)).toBe('active');
    expect(phaseOfView('potentieel')).toBe('potential');
    expect(phaseOfView('afgesloten')).toBe('closed');
    expect(phaseOfView('iets')).toBe('active');
    expect(viewHref('/opdrachten', 'active')).toBe('/opdrachten');
    expect(viewHref('/opdrachten', 'potential')).toBe('/opdrachten?weergave=potentieel');
  });

  it('keeps the search across the views and starts each at its first page', () => {
    expect(viewHref('/opdrachten', 'active', 'alfa')).toBe('/opdrachten?zoek=alfa');
    expect(viewHref('/opdrachten', 'closed', 'a & b')).toBe(
      '/opdrachten?weergave=afgesloten&zoek=a+%26+b',
    );
  });

  it('says how long something has been in a state', () => {
    const now = new Date('2026-03-15T10:00:00');
    expect(durationText(daysSince('2026-03-15', now))).toBe('vandaag');
    expect(durationText(daysSince('2026-03-14', now))).toBe('1 dag');
    expect(durationText(daysSince('2026-03-03', now))).toBe('12 dagen');
    expect(durationText(daysSince('2026-02-08', now))).toBe('5 weken');
    expect(durationText(daysSince('2025-11-15', now))).toBe('4 maanden');
    expect(durationText(daysSince(null, now))).toBe('');
  });
});

describe('assignmentInput', () => {
  it('asks only for a name, the kind and the client when creating', () => {
    const form = { ...initialState(), name: ' Opdracht Gamma ', clientId: 'o1', notes: 'later' };
    expect(assignmentInput(form, true)).toEqual({
      name: 'Opdracht Gamma',
      kind: 'external',
      client_organisation_id: 'o1',
    });
  });

  it('sends no client for an internal assignment', () => {
    const form = { ...initialState(), name: 'Kennisdeling', kind: 'internal', clientId: 'o1' };
    expect(assignmentInput(form, true)).toMatchObject({ client_organisation_id: null });
  });

  it('sends the rest when editing, and never an exchange form', () => {
    const form = { ...initialState(assignment()), clientContact: ' Afdeling X ' };
    const input = assignmentInput(form, false);
    expect(input).toMatchObject({ client_contact: 'Afdeling X', start_date: '2026-01-01' });
    expect(input).not.toHaveProperty('traffic_form');
  });

  it('needs a name', () => {
    expect(assignmentInput(initialState(), true)).toBe('Geef de opdracht een naam.');
  });
});
