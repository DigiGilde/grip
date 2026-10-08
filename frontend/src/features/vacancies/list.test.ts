import { describe, expect, it } from 'vitest';
import type { VacancySummary } from './api';
import { orderVacancies, standingOf } from './list';
import { STEP_NAMES, vacancySteps } from './steps';

const NOW = new Date(2026, 9, 8); // 8 October 2026

function row(id: string, extra: Partial<VacancySummary>): VacancySummary {
  return { id, function_title: id, fte: '1.00', status: 'requested', ...extra };
}

describe('standingOf', () => {
  it('names the step as the step bar does, with what it waits on', () => {
    const standing = standingOf(
      row('a', { step: 'decide', step_detail: 'Wacht op advies HR', step_since: '2026-10-07' }),
      NOW,
    );
    expect(standing).toEqual({ step: 'Advies en akkoord', detail: 'Wacht op advies HR' });
    expect(standing.step).toBe(STEP_NAMES.decide);
  });

  it('says how long it waits once that is more than a few days', () => {
    const waiting = (since: string) =>
      standingOf(row('a', { step: 'decide', step_detail: 'Wacht op akkoord', step_since: since }), NOW)
        .detail;
    expect(waiting('2026-10-05')).toBe('Wacht op akkoord');
    expect(waiting('2026-10-04')).toBe('Wacht op akkoord, al 4 dagen');
    expect(waiting('2026-09-01')).toBe('Wacht op akkoord, al 5 weken');
  });

  it('shows no step once nothing is next, only since when', () => {
    const ended = standingOf(
      row('a', { status: 'filled', step: null, step_since: '2026-10-01' }),
      NOW,
    );
    expect(ended).toEqual({ step: '', detail: 'Sinds 1 okt 2026' });
    // A reader of the published vacancy only gets no step at all.
    expect(standingOf(row('a', { status: 'open' }), NOW)).toEqual({ step: '', detail: '' });
  });

  it('uses the same words as the step bar of the vacancy page', () => {
    const steps = vacancySteps({
      id: 'v',
      function_title: 'x',
      fte: '1.00',
      status: 'draft',
      procedure: [],
      decisions: [],
      texts: [],
      permissions: {
        can_edit: true,
        can_record_hr_advice: false,
        can_record_control_advice: false,
        can_record_approval: false,
        can_download_form: false,
      },
    })!;
    expect(steps.items).toEqual(Object.values(STEP_NAMES));
  });
});

describe('orderVacancies', () => {
  const rows = [
    row('nieuw', { step: 'prepare', step_since: '2026-10-08' }),
    row('klaar', { status: 'filled', step: null, step_since: '2026-06-01' }),
    row('wacht-lang', { step: 'decide', step_since: '2026-09-01' }),
    row('wacht-kort', { step: 'decide', step_since: '2026-10-03' }),
  ];
  const ids = (order: 'waiting' | 'newest' | 'function') =>
    orderVacancies(rows, order, NOW).map((vacancy) => vacancy.id);

  it('puts what waits longest first and what has ended last', () => {
    expect(ids('waiting')).toEqual(['wacht-lang', 'wacht-kort', 'nieuw', 'klaar']);
  });

  it('can keep the order of arrival or sort on the function', () => {
    expect(ids('newest')).toEqual(['nieuw', 'klaar', 'wacht-lang', 'wacht-kort']);
    expect(ids('function')).toEqual(['klaar', 'nieuw', 'wacht-kort', 'wacht-lang']);
  });
});
