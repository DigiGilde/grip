import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/client';
import { ConflictPanel } from './ConflictPanel';
import { ifMatch, staleConflictOf } from './stale';

describe('a save on top of a colleague', () => {
  it('names the record and the version it started from', () => {
    expect(ifMatch('abc', 3)).toEqual({ 'If-Match': '"abc:3"' });
    expect(ifMatch('abc', undefined)).toBeUndefined();
    expect(ifMatch(null, 3)).toBeUndefined();
  });

  it('tells a refused stale save apart from any other conflict', () => {
    const stale = new ApiError(
      409,
      'Conflict',
      {},
      {
        code: 'StaleWriteError',
        detail: 'Eva Eigenaar heeft deze begrotingsregel intussen gewijzigd.',
        changed_by: 'Eva Eigenaar',
        changed_at: '2026-10-09T08:00:00+00:00',
      },
    );
    expect(staleConflictOf(stale)).toEqual({
      message: 'Eva Eigenaar heeft deze begrotingsregel intussen gewijzigd.',
      changedBy: 'Eva Eigenaar',
      changedAt: '2026-10-09T08:00:00+00:00',
    });
    const closed = new ApiError(
      409,
      'Conflict',
      {},
      { code: 'MonthClosedError', detail: 'Dicht.' },
    );
    expect(staleConflictOf(closed)).toBeNull();
    expect(staleConflictOf(new Error('netwerk'))).toBeNull();
  });

  it('shows only what differs, theirs next to the own, and both ways on', () => {
    const keep = vi.fn();
    const take = vi.fn();
    const { container } = render(
      <ConflictPanel
        conflict={{
          message: 'Eva heeft dit intussen gewijzigd.',
          changedBy: 'Eva',
          changedAt: null,
        }}
        theirs={[
          { label: 'Rol', value: 'Developer' },
          { label: 'FTE', value: '0,5' },
        ]}
        mine={[
          { label: 'Rol', value: 'Developer' },
          { label: 'FTE', value: '0,8' },
        ]}
        onKeepMine={keep}
        onTakeTheirs={take}
      />,
    );
    expect(container.querySelector('nldd-banner')?.getAttribute('text')).toBe(
      'Eva heeft dit intussen gewijzigd.',
    );
    const rows = [...container.querySelectorAll('nldd-table-row:not([slot])')].map((row) =>
      [...row.querySelectorAll('nldd-text-cell')].map((cell) => cell.getAttribute('text')),
    );
    expect(rows).toEqual([['FTE', '0,5', '0,8']]);
    const buttons = [...container.querySelectorAll('nldd-button')].map((button) =>
      button.getAttribute('text'),
    );
    expect(buttons).toEqual(['Bewaar mijn wijziging', 'Neem de andere over']);
  });
});
