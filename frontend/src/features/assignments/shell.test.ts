import { describe, expect, it } from 'vitest';
import { visibleTabs } from './shell';
import { NO_PERMISSIONS, PERMISSIONS, assignment } from './testing';
import { countByPhase, daysSince, durationText, phaseOfView, viewHref } from './views';
import { assignmentInput, initialState } from './assignmentForm';

describe('visibleTabs', () => {
  it('gives an owner every tab', () => {
    expect(visibleTabs(PERMISSIONS.owner)).toEqual([
      'overview',
      'tasks',
      'finance',
      'staffing',
      'budget',
      'quote',
      'monthClose',
      'history',
    ]);
  });

  it('gives a planner the people, and the monthly close, but no money', () => {
    expect(visibleTabs(PERMISSIONS.planner)).toEqual([
      'overview',
      'tasks',
      'staffing',
      'monthClose',
      'history',
    ]);
  });

  it('gives a team member the team by name and nothing else', () => {
    expect(visibleTabs(PERMISSIONS.member)).toEqual(['overview', 'tasks', 'staffing', 'history']);
  });

  it('gives a lezer the money and no people', () => {
    expect(visibleTabs(PERMISSIONS.lezer)).toEqual([
      'overview',
      'tasks',
      'finance',
      'budget',
      'quote',
      'monthClose',
      'history',
    ]);
  });

  it('leaves the overview, the tasks and the history without any permission', () => {
    expect(visibleTabs(NO_PERMISSIONS)).toEqual(['overview', 'tasks', 'history']);
  });
});

describe('list views', () => {
  it('shows running work by default and reads the view from the address', () => {
    expect(phaseOfView(null)).toBe('active');
    expect(phaseOfView('pijplijn')).toBe('potential');
    expect(phaseOfView('afgesloten')).toBe('closed');
    expect(phaseOfView('iets')).toBe('active');
    expect(viewHref('/opdrachten', 'active')).toBe('/opdrachten');
    expect(viewHref('/opdrachten', 'potential')).toBe('/opdrachten?weergave=pijplijn');
  });

  it('counts per phase', () => {
    const items = [
      assignment(),
      assignment({ phase: 'potential' }),
      assignment({ phase: 'potential' }),
    ];
    expect(countByPhase(items)).toEqual({ potential: 2, active: 1, closed: 0 });
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
