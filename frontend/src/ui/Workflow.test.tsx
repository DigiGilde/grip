import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Course } from './course';
import { CourseBar } from './Workflow';

afterEach(() => vi.unstubAllGlobals());

const COURSE: Course = {
  key: 'akkoord',
  label: 'Naar een akkoord',
  steps: [
    { key: 'begroting', label: 'Begroting', state: 'done', note: 'Vastgesteld op 2 november' },
    { key: 'offerte', label: 'Offerte', state: 'current' },
    { key: 'aanbieden', label: 'Aanbieden', state: 'future' },
    { key: 'akkoord', label: 'Akkoord', state: 'future' },
  ],
};

function narrowScreen() {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

describe('CourseBar', () => {
  it('draws every step with its status and marks the current one', () => {
    const { container } = render(<CourseBar course={COURSE} accessibleLabel="Verloop van Alfa" />);
    expect(container.querySelector('nldd-step-bar')?.getAttribute('accessible-label')).toBe(
      'Verloop van Alfa',
    );
    expect(
      [...container.querySelectorAll('nldd-step-bar-item')].map((item) => [
        item.getAttribute('text'),
        item.getAttribute('status'),
      ]),
    ).toEqual([
      ['Begroting', 'past'],
      ['Offerte', 'current'],
      ['Aanbieden', 'future'],
      ['Akkoord', 'future'],
    ]);
    expect(container.querySelectorAll('nldd-step-bar-item[status="current"]')).toHaveLength(1);
  });

  it('says what happened at the steps that are done', () => {
    const { container } = render(<CourseBar course={COURSE} accessibleLabel="Verloop" />);
    expect(container.textContent).toContain('Begroting: vastgesteld op 2 november');
  });

  it('gives the step it is at and the one after in words on a narrow screen', () => {
    narrowScreen();
    const { container } = render(<CourseBar course={COURSE} accessibleLabel="Verloop van Alfa" />);
    expect(container.querySelector('nldd-step-bar')).toBeNull();
    const words = container.querySelector('[role="group"][aria-label="Verloop van Alfa"]');
    expect(words?.textContent).toBe('Offerte, daarna aanbieden');
  });

  it('draws nothing without steps', () => {
    const { container } = render(
      <CourseBar course={{ ...COURSE, steps: [] }} accessibleLabel="Verloop" />,
    );
    expect(container.firstChild).toBeNull();
  });
});
