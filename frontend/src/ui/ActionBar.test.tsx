import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ActionBar } from './ActionBar';

const OPTIONS = [
  { value: '2026', label: '2026' },
  { value: 'all', label: 'Hele looptijd' },
];

describe('ActionBar', () => {
  it('draws every control at the same size step, inside one toolbar', () => {
    const { container } = render(
      <ActionBar
        label="Inzet: weergave"
        filters={[{ label: 'Jaar', value: '2026', onChange: () => {}, options: OPTIONS }]}
        actions={[{ text: 'Nieuwe inzet', onClick: () => {}, primary: true }]}
      />,
    );
    const toolbar = container.querySelector('nldd-toolbar');
    expect(toolbar).toHaveAttribute('label', 'Inzet: weergave');
    const sizes = [toolbar, ...container.querySelectorAll('nldd-dropdown, nldd-button')].map((el) =>
      el?.getAttribute('size'),
    );
    expect(sizes).toEqual(['md', 'md', 'md']);
  });

  it('puts filters at the start and actions at the end, the primary one last to overflow', () => {
    const { container } = render(
      <ActionBar
        label="x"
        filters={[{ label: 'Jaar', value: '2026', onChange: () => {}, options: OPTIONS }]}
        actions={[
          { text: 'Download', href: '/api/x.csv' },
          { text: 'Nieuw', onClick: () => {}, primary: true },
        ]}
      />,
    );
    const items = [...container.querySelectorAll('nldd-toolbar-item')];
    expect(items.map((item) => item.getAttribute('slot'))).toEqual(['start', 'end', 'end']);
    expect(items.map((item) => item.getAttribute('priority'))).toEqual(['1', '2', '3']);
    expect(container.querySelector('nldd-button[href="/api/x.csv"]')).not.toBeNull();
  });

  it('gives every control an alternative in the overflow menu', () => {
    const { container } = render(
      <ActionBar
        label="x"
        filters={[{ label: 'Jaar', value: 'all', onChange: () => {}, options: OPTIONS }]}
        actions={[{ text: 'Nieuw', onClick: () => {} }]}
      />,
    );
    for (const item of container.querySelectorAll('nldd-toolbar-item')) {
      expect(item.querySelector('[slot="overflow"]')).not.toBeNull();
    }
    const radios = [...container.querySelectorAll('nldd-menu-item[type="radio"]')];
    expect(radios.map((r) => r.hasAttribute('selected'))).toEqual([false, true]);
  });

  it('reports a chosen filter value and a clicked action', () => {
    const onChange = vi.fn();
    const onClick = vi.fn();
    const { container } = render(
      <ActionBar
        label="x"
        filters={[{ label: 'Jaar', value: '2026', onChange, options: OPTIONS }]}
        actions={[{ text: 'Nieuw', onClick }]}
      />,
    );
    container
      .querySelector('nldd-dropdown')
      ?.dispatchEvent(new CustomEvent('change', { detail: { value: 'all' } }));
    expect(onChange).toHaveBeenCalledWith('all');
    container.querySelector('nldd-button')?.dispatchEvent(new Event('click'));
    container.querySelector('nldd-menu-item[slot="overflow"]')?.dispatchEvent(new Event('select'));
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it('renders nothing without filters or actions', () => {
    const { container } = render(<ActionBar label="x" />);
    expect(container.firstChild).toBeNull();
  });
});
