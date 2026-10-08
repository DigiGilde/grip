import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AssignmentShellContext } from './shell';
import { AssignmentTab } from './TabGuard';
import type { AssignmentDetail } from './api';

function shell(read_financial: boolean): AssignmentDetail {
  return {
    id: 'a-1',
    permissions: {
      read_financial,
      read_staffing: false,
      read_roster: true,
      edit_basic: false,
      edit_financial: false,
      edit_staffing: false,
    },
  } as unknown as AssignmentDetail;
}

describe('a tab of an assignment the reader does not have', () => {
  it('says no access instead of rendering the tab', () => {
    const { container } = render(
      <AssignmentShellContext.Provider value={shell(false)}>
        <AssignmentTab tab="finance">
          <p data-testid="tab">bedragen</p>
        </AssignmentTab>
      </AssignmentShellContext.Provider>,
    );
    expect(container.querySelector('[data-testid="tab"]')).toBeNull();
    const state = container.querySelector('[data-state="no-access"]');
    expect(state?.textContent).toContain('De bedragen van deze opdracht zijn voor');
    // Nothing of the tab's own actions, only the way back.
    expect(container.querySelector('nldd-button')?.getAttribute('text')).toBe('Naar het overzicht');
  });

  it('renders the tab for who has it', () => {
    const { container } = render(
      <AssignmentShellContext.Provider value={shell(true)}>
        <AssignmentTab tab="finance">
          <p data-testid="tab">bedragen</p>
        </AssignmentTab>
      </AssignmentShellContext.Provider>,
    );
    expect(container.querySelector('[data-testid="tab"]')).not.toBeNull();
    expect(container.querySelector('[data-state="no-access"]')).toBeNull();
  });
});
