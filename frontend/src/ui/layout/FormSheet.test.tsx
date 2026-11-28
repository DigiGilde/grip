import { act, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FormSheet } from './FormSheet';

function announced(): string {
  return document.getElementById('grip-announcer')?.textContent ?? '';
}

function Sheet({ open, onSubmit = () => {} }: { open: boolean; onSubmit?: () => void }) {
  return (
    <FormSheet
      open={open}
      title="Wijzig gegevens"
      submitText="Bewaar gegevens"
      onSubmit={onSubmit}
      onClose={() => {}}
    >
      <span>veld</span>
    </FormSheet>
  );
}

describe('FormSheet', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    document.getElementById('grip-announcer')?.remove();
  });

  it('says that it saved when it closes after the form was sent', () => {
    const onSubmit = vi.fn();
    const { rerender } = render(<Sheet open onSubmit={onSubmit} />);
    // The region is there before the first message, or that one is not read.
    const region = document.getElementById('grip-announcer');
    expect(region).toHaveAttribute('role', 'status');
    expect(region).toHaveAttribute('aria-live', 'polite');

    fireEvent.submit(document.querySelector('nldd-form') as HTMLElement);
    expect(onSubmit).toHaveBeenCalledOnce();
    rerender(<Sheet open={false} onSubmit={onSubmit} />);
    act(() => void vi.advanceTimersByTime(100));
    expect(announced()).toBe('Wijzig gegevens: opgeslagen');
  });

  it('says nothing when it is dismissed', () => {
    const { rerender } = render(<Sheet open />);
    fireEvent(
      document.querySelector('nldd-top-title-bar') as HTMLElement,
      new CustomEvent('dismiss'),
    );
    rerender(<Sheet open={false} />);
    act(() => void vi.advanceTimersByTime(100));
    expect(announced()).toBe('');
  });

  it('says nothing when a sent form is dismissed after a refusal', () => {
    const { rerender } = render(<Sheet open />);
    fireEvent.submit(document.querySelector('nldd-form') as HTMLElement);
    fireEvent(document.querySelector('nldd-sheet') as HTMLElement, new CustomEvent('close'));
    rerender(<Sheet open={false} />);
    act(() => void vi.advanceTimersByTime(100));
    expect(announced()).toBe('');
  });

  it('names the sheet by its title and puts the way out in the title bar', () => {
    render(<Sheet open />);
    const bar = document.querySelector('nldd-top-title-bar');
    expect(bar).toHaveAttribute('text', 'Wijzig gegevens');
    expect(bar).toHaveAttribute('dismiss-text', 'Annuleer');
    expect(document.querySelector('nldd-sheet nldd-title')).toHaveAttribute('heading-level', '1');
    expect(document.querySelector('nldd-sheet')).toHaveAttribute(
      'accessible-label',
      'Wijzig gegevens',
    );
  });

  it('does not send a form with text in a date field that is no date, and says so', () => {
    const onSubmit = vi.fn();
    render(
      <FormSheet open title="Looptijd" submitText="Bewaar" onSubmit={onSubmit} onClose={() => {}}>
        <nldd-date-field />
      </FormSheet>,
    );
    const field = document.querySelector('nldd-date-field') as HTMLElement & {
      ownValidity: () => { flags: { badInput: boolean } };
    };
    field.ownValidity = () => ({ flags: { badInput: true } });
    fireEvent.submit(document.querySelector('nldd-form') as HTMLElement);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(document.querySelector('nldd-banner')).toHaveAttribute('text', 'Dit is geen datum');
    expect(field).toHaveProperty('invalid', true);
  });
});
