import { act, fireEvent, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ActionBar } from './ActionBar';

const OPTIONS = [
  { value: '2026', label: '2026' },
  { value: 'all', label: 'Hele looptijd' },
];

describe('ActionBar', () => {
  it('shows a single control without a toolbar', () => {
    const { container } = render(
      <ActionBar label="x" actions={[{ text: 'Wijzig de looptijd', onClick: () => {} }]} />,
    );
    expect(container.querySelector('nldd-toolbar')).toBeNull();
    expect(container.querySelector('nldd-button')).toHaveAttribute('size', 'md');
  });

  it('draws every control at the same size step, inside one toolbar', () => {
    const { container } = render(
      <ActionBar
        label="Inzet: weergave"
        filters={[{ label: 'Jaar', value: '2026', onChange: () => {}, options: OPTIONS }]}
        actions={[{ text: 'Nieuwe inzet', onClick: () => {}, primary: true }]}
      />,
    );
    const toolbar = container.querySelector('nldd-toolbar');
    expect(toolbar).toHaveAttribute('accessible-label', 'Inzet: weergave');
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
    expect(items.map((item) => item.getAttribute('priority'))).toEqual(['2', '1', '3']);
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

  it('gives the rare actions an alternative too, behind the same confirmation', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <ActionBar
        label="x"
        filters={[{ label: 'Jaar', value: 'all', onChange: () => {}, options: OPTIONS }]}
        more={{
          name: 'kostenpost Zaal',
          actions: [
            {
              text: 'Verwijder',
              destructive: true,
              confirm: { text: 'Deze kostenpost verwijderen?', confirmText: 'Verwijder kostenpost' },
              onSelect,
            },
          ],
        }}
      />,
    );
    for (const item of container.querySelectorAll('nldd-toolbar-item')) {
      expect(item.querySelector('[slot="overflow"]')).not.toBeNull();
    }
    const item = container.querySelector(
      'nldd-menu-item[slot="overflow"][text="Verwijder kostenpost Zaal"]',
    );
    expect(item?.hasAttribute('destructive')).toBe(true);
    act(() => {
      item?.dispatchEvent(new Event('select'));
    });
    expect(onSelect).not.toHaveBeenCalled();
    const dialog = document.body.querySelector(
      'nldd-modal-dialog[text="Deze kostenpost verwijderen?"]',
    );
    expect(dialog?.hasAttribute('open')).toBe(true);
    act(() => {
      dialog
        ?.querySelector('nldd-button[text="Verwijder kostenpost"]')
        ?.dispatchEvent(new Event('click'));
    });
    expect(onSelect).toHaveBeenCalledTimes(1);
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
    fireEvent.change(container.querySelector('nldd-dropdown select') as HTMLSelectElement, {
      target: { value: 'all' },
    });
    expect(onChange).toHaveBeenCalledTimes(1);
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
