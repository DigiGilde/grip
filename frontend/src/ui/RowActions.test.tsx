import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RowActions, RowActionsHeader } from './RowActions';

describe('RowActions', () => {
  it('names the menu button with the row it belongs to', () => {
    const { container } = render(
      <RowActions
        name="Priya Product"
        actions={[
          { text: 'Wijzig', onSelect: () => {} },
          { text: 'Heropen', onSelect: () => {} },
        ]}
      />,
    );
    const button = container.querySelector('nldd-icon-button');
    expect(button).toHaveAttribute('accessible-label', 'Meer acties voor Priya Product');
    expect(button).toHaveAttribute('popup-type', 'menu');
  });

  it('puts a destructive action last, behind a divider', () => {
    const { container } = render(
      <RowActions
        name="Rij"
        actions={[
          { text: 'Verwijder', destructive: true },
          { text: 'Bekijk inzet', href: '/inzet' },
        ]}
      />,
    );
    const menu = container.querySelector('nldd-menu') as Element;
    expect([...menu.children].map((el) => el.localName)).toEqual([
      'nldd-menu-item',
      'nldd-menu-divider',
      'nldd-menu-item',
    ]);
    expect(menu.lastElementChild).toHaveAttribute('text', 'Verwijder');
  });

  it('shows a lone removal as its button, not as a menu', () => {
    const { container } = render(
      <RowActions name="Hosting" actions={[{ text: 'Verwijder', destructive: true }]} />,
    );
    expect(container.querySelector('nldd-menu')).toBeNull();
    expect(container.querySelector('nldd-icon-button')).toHaveAttribute(
      'accessible-label',
      'Verwijder Hosting',
    );
  });

  it('shows a lone withdrawal with another picture than the trash can', () => {
    const remove = render(
      <RowActions name="Hosting" actions={[{ text: 'Verwijder', destructive: true }]} />,
    ).container.querySelector('nldd-icon-button');
    const withdraw = render(
      <RowActions
        name="passkey Telefoon"
        actions={[{ text: 'Trek in', destructive: true, withdraws: true }]}
      />,
    ).container.querySelector('nldd-icon-button');
    expect(withdraw).toHaveAttribute('accessible-label', 'Trek in passkey Telefoon');
    expect(withdraw?.getAttribute('icon')).not.toBe(remove?.getAttribute('icon'));
  });

  it('gives the actions column a header that is read out and not shown', () => {
    const { container } = render(<RowActionsHeader />);
    const cell = container.querySelector('nldd-cell');
    expect(cell).toHaveTextContent('Acties');
    expect(cell?.querySelector('span')).toHaveClass('grip-visually-hidden');
  });
});
