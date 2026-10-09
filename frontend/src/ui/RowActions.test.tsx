import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RowActions, RowActionsHeader } from './RowActions';

describe('RowActions', () => {
  it('names the menu button with the row it belongs to', () => {
    const { container } = render(
      <RowActions name="Priya Product" actions={[{ text: 'Wijzig', onSelect: () => {} }]} />,
    );
    const button = container.querySelector('nldd-icon-button');
    expect(button).toHaveAttribute('accessible-label', 'Meer acties voor Priya Product');
    expect(button).toHaveAttribute('popup-type', 'menu');
  });

  it('gives the actions column a header that is read out and not shown', () => {
    const { container } = render(<RowActionsHeader />);
    const cell = container.querySelector('nldd-cell');
    expect(cell).toHaveTextContent('Acties');
    expect(cell?.querySelector('span')).toHaveClass('grip-visually-hidden');
  });
});
