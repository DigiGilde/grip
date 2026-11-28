import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { TabNav } from './TabNav';

const ITEMS = [
  { key: 'close', text: 'Afsluiten en factureren', short: 'Afsluiten', href: '/a/afsluiten' },
  { key: 'budget', text: 'Begroting', href: '/a/begroting' },
];

function narrowWindow(narrow: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation(() => ({
      matches: narrow,
      addEventListener: () => {},
      removeEventListener: () => {},
    })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('TabNav', () => {
  it('draws one menu bar with the current item marked, never a select', () => {
    narrowWindow(false);
    const { container } = renderApp(
      <TabNav label="Onderdelen van Alfa" items={ITEMS} current="budget" narrow="bar" />,
    );
    const items = [...container.querySelectorAll('nldd-menu-bar-item')];
    expect(items.map((item) => item.getAttribute('text'))).toEqual([
      'Afsluiten en factureren',
      'Begroting',
    ]);
    expect(items.map((item) => item.hasAttribute('current'))).toEqual([false, true]);
    expect(container.querySelector('select, nldd-dropdown')).toBeNull();
  });

  it('draws nothing on a narrow screen when the parts are left to the landing', () => {
    narrowWindow(true);
    const { container } = renderApp(
      <TabNav label="Onderdelen van Alfa" items={ITEMS} current="budget" narrow="hide" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('keeps the bar on a narrow screen, with the short text, never a select', () => {
    narrowWindow(true);
    const { container } = renderApp(
      <TabNav label="Weergave" items={ITEMS} current="close" narrow="bar" />,
    );
    const items = [...container.querySelectorAll('nldd-menu-bar-item')];
    expect(items.map((item) => item.getAttribute('text'))).toEqual(['Afsluiten', 'Begroting']);
    expect(container.querySelector('select, nldd-dropdown')).toBeNull();
  });

  it('keeps the bar on a wide screen when the parts are hidden on a narrow one', () => {
    narrowWindow(false);
    const { container } = renderApp(
      <TabNav label="Onderdelen van Alfa" items={ITEMS} current="budget" narrow="hide" />,
    );
    expect(container.querySelectorAll('nldd-menu-bar-item')).toHaveLength(2);
  });
});
