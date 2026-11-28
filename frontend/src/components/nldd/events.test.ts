import { afterEach, describe, expect, it, vi } from 'vitest';
import { afterMenuCloses } from './events';

/** An item in a menu that says itself whether it is open, as jsdom opens no popovers. */
function menuWithItem(open: boolean) {
  const menu = document.createElement('nldd-menu');
  const item = document.createElement('nldd-menu-item');
  menu.append(item);
  document.body.append(menu);
  const matches = menu.matches.bind(menu);
  Object.defineProperty(menu, 'matches', {
    value: (selector: string) => (selector === ':popover-open' ? open : matches(selector)),
  });
  return { menu, item };
}

function choose(item: Element, action: () => void) {
  item.addEventListener('select', (event) => afterMenuCloses(event, action));
  item.dispatchEvent(new Event('select', { bubbles: true }));
}

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
});

describe('afterMenuCloses', () => {
  it('waits until the open menu of the chosen item has closed, and acts once', () => {
    vi.useFakeTimers();
    const { menu, item } = menuWithItem(true);
    const action = vi.fn();
    choose(item, action);
    expect(action).not.toHaveBeenCalled();
    menu.dispatchEvent(new Event('toggle'));
    expect(action).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(2000);
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('acts at once when the menu is not open', () => {
    const { item } = menuWithItem(false);
    const action = vi.fn();
    choose(item, action);
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('acts at once for an item outside a menu', () => {
    const item = document.createElement('nldd-menu-item');
    document.body.append(item);
    const action = vi.fn();
    choose(item, action);
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('still acts when the menu never says that it closed', () => {
    vi.useFakeTimers();
    const { item } = menuWithItem(true);
    const action = vi.fn();
    choose(item, action);
    vi.advanceTimersByTime(1000);
    expect(action).toHaveBeenCalledTimes(1);
  });
});
