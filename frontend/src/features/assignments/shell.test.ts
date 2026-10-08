import { describe, expect, it } from 'vitest';
import { nextSteps } from './steps';
import { visibleTabs } from './shell';
import { NO_PERMISSIONS, PERMISSIONS, assignment } from './testing';
import { countByPhase, daysSince, durationText, phaseOfView, viewHref } from './views';
import { assignmentInput, initialState } from './assignmentForm';

describe('visibleTabs', () => {
  it('gives an owner every tab', () => {
    expect(visibleTabs(PERMISSIONS.owner)).toEqual([
      'overview',
      'finance',
      'staffing',
      'budget',
      'quote',
      'monthClose',
    ]);
  });

  it('gives a planner the people, and the monthly close, but no money', () => {
    expect(visibleTabs(PERMISSIONS.planner)).toEqual(['overview', 'staffing', 'monthClose']);
  });

  it('gives a team member the team by name and nothing else', () => {
    expect(visibleTabs(PERMISSIONS.member)).toEqual(['overview', 'staffing']);
  });

  it('gives a lezer the money and no people', () => {
    expect(visibleTabs(PERMISSIONS.lezer)).toEqual(['overview', 'finance', 'budget', 'quote', 'monthClose']);
  });

  it('leaves only the overview without any permission', () => {
    expect(visibleTabs(NO_PERMISSIONS)).toEqual(['overview']);
  });
});

describe('nextSteps', () => {
  const potential = (overrides = {}) =>
    assignment({ phase: 'potential', status: 'draft', ...overrides });

  it('has nothing to say once the assignment is agreed', () => {
    expect(nextSteps(assignment())).toBeNull();
  });

  it('starts at the budget', () => {
    const steps = nextSteps(potential());
    expect(steps?.current).toBe(1);
    expect(steps?.items.map((item) => item.tab)).toEqual(['budget', 'quote', 'quote', undefined]);
  });

  it('moves to offering once a quote exists', () => {
    expect(nextSteps(potential({ pipeline_amount_source: 'quote' }))?.current).toBe(3);
  });

  it('waits for the client after the quote went out, also after a verbal yes', () => {
    expect(nextSteps(potential({ status: 'quoted' }))?.current).toBe(4);
    const verbal = nextSteps(potential({ status: 'verbally_agreed' }));
    expect(verbal?.current).toBe(4);
    expect(verbal?.advice).toContain('mondeling');
  });

  it('carries the one action of the page on the current step', () => {
    expect(nextSteps(potential())?.action).toEqual({ text: 'Maak de begroting', tab: 'budget' });
    expect(nextSteps(potential({ pipeline_amount_source: 'quote' }))?.action?.text).toBe(
      'Bied de offerte aan',
    );
  });

  it('says whose turn it is to a reader who cannot take the step', () => {
    const steps = nextSteps(potential({ permissions: PERMISSIONS.planner }));
    expect(steps?.items.every((item) => item.tab === undefined)).toBe(true);
    expect(steps?.action).toBeNull();
    expect(steps?.advice).toContain('Voorbeeld Eigenaar maakt eerst de begroting');
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
    const items = [assignment(), assignment({ phase: 'potential' }), assignment({ phase: 'potential' })];
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
