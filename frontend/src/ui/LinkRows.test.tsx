import { describe, expect, it } from 'vitest';
import { renderApp } from '@/test/utils';
import { LinkRows } from './LinkRows';

describe('LinkRows', () => {
  it('names the list and draws a row per entry', () => {
    const { container } = renderApp(
      <LinkRows
        label="Onderdelen"
        rows={[
          { key: 'a', text: 'Begroting' },
          { key: 'b', text: 'Offerte' },
        ]}
      />,
    );
    expect(container.querySelector('nldd-list')).toHaveAttribute('accessible-label', 'Onderdelen');
    expect(container.querySelectorAll('nldd-list-item')).toHaveLength(2);
  });

  it('ends a row with an address on the open mark, and a row without one on nothing', () => {
    const { container } = renderApp(
      <LinkRows
        label="Onderdelen"
        rows={[
          { key: 'a', text: 'Begroting', href: '/a/begroting' },
          { key: 'b', text: 'Offerte' },
        ]}
      />,
    );
    const [linked, plain] = [...container.querySelectorAll('nldd-list-item')];
    expect(linked).toHaveAttribute('href', '/a/begroting');
    expect(linked?.querySelector('nldd-icon-cell nldd-icon')).toHaveAttribute(
      'icon',
      'chevron-right',
    );
    expect(plain).not.toHaveAttribute('href');
    expect(plain?.querySelector('nldd-icon-cell')).toBeNull();
  });

  it('puts the notice under the text and the tag and the end value on the row', () => {
    const { container } = renderApp(
      <LinkRows
        label="Onderdelen"
        rows={[
          {
            key: 'a',
            text: 'Afsluiten en factureren',
            notice: 'Maart is nog open',
            tag: { text: 'Te laat', color: 'critical' },
            end: '€ 3.000',
          },
        ]}
      />,
    );
    const row = container.querySelector('nldd-list-item');
    const text = row?.querySelector('nldd-text-cell');
    expect(text).toHaveAttribute('text', 'Afsluiten en factureren');
    expect(text).toHaveAttribute('supporting-text', 'Maart is nog open');
    expect(row?.querySelector('nldd-badge')).toHaveAttribute('text', 'Te laat');
    expect(row?.querySelector('nldd-badge')).toHaveAttribute('color', 'critical');
    expect(row).toHaveTextContent('€ 3.000');
  });
});
