/**
 * The tabs of one open thing (an assignment, a vacancy) or the views of a
 * list: each a page with its own address. They read as sides of the thing,
 * never as buttons: plain text on one line with a hairline under the row and
 * a line under the tab you are on. Nothing is filled; the only filled accent
 * on a page is its primary action. The bar stays a bar on every width; a row
 * that does not fit puts the rest behind the bar's own "Meer".
 */
import { useRef } from 'react';
import { orUndef } from '@/components/nldd/events';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { useNarrow } from './useNarrow';

export interface TabNavItem {
  key: string;
  text: string;
  /** What the item says on a narrow screen, when `text` is too long for it. */
  short?: string;
  href: string;
}

export interface TabNavProps {
  /** Accessible name: "Onderdelen van <naam>". */
  label: string;
  items: readonly TabNavItem[];
  current: string;
  /**
   * What a narrow screen shows. 'hide' for the parts of a thing: switching
   * between them goes through its landing. 'bar' for the views of a list.
   */
  narrow?: 'hide' | 'bar';
}

export function TabNav({ label, items, current, narrow = 'bar' }: TabNavProps) {
  const ref = useRef<HTMLElement>(null);
  const isNarrow = useNarrow();
  useRouterLinks(ref);

  if (isNarrow && narrow === 'hide') return null;
  // Each tab is a page with its own address, so this is navigation between
  // pages: links in a nav landmark, the current one marked `aria-current`.
  // The design system's menu bar draws exactly that, with a line under the
  // current page. Its tab bar is a segmented control: the current tab is a
  // filled accent pill that reads as a second primary button.
  return (
    <div className="thing-tabs">
      <nldd-menu-bar ref={ref} accessible-label={label}>
        {items.map((item) => (
          <nldd-menu-bar-item
            key={item.key}
            href={item.href}
            text={isNarrow ? (item.short ?? item.text) : item.text}
            current={orUndef(item.key === current)}
          />
        ))}
      </nldd-menu-bar>
    </div>
  );
}
