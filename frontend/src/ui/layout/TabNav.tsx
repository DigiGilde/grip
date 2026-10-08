/**
 * The tabs of one open thing (an assignment, a vacancy): each tab a page with
 * its own address. They read as sides of the thing, never as buttons: plain
 * text on one line with a hairline under the row and a line under the tab
 * you are on. Nothing is filled; the only filled accent on a page is its
 * primary action. On a narrow screen the same choice is one select, because
 * a row that does not fit hides its labels.
 */
import { useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { orUndef } from '@/components/nldd/events';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { FilterSelect } from './FilterSelect';
import { useNarrow } from './useNarrow';

export interface TabNavItem {
  key: string;
  text: string;
  href: string;
}

interface TabNavProps {
  /** Accessible name: "Onderdelen van <naam>". */
  label: string;
  items: readonly TabNavItem[];
  current: string;
}

/** Below this width the tabs become a select. */
const NARROW = '(max-width: 720px)';

export function TabNav({ label, items, current }: TabNavProps) {
  const ref = useRef<HTMLElement>(null);
  const navigate = useNavigate();
  const narrow = useNarrow(NARROW);
  useRouterLinks(ref);

  if (narrow) {
    return (
      <nav aria-label={label}>
        <FilterSelect
          label={label}
          value={current}
          onChange={(key) => {
            const item = items.find((candidate) => candidate.key === key);
            if (item && item.key !== current) navigate(item.href);
          }}
          options={items.map((item) => ({ value: item.key, label: item.text }))}
          width="100%"
        />
      </nav>
    );
  }
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
            text={item.text}
            current={orUndef(item.key === current)}
          />
        ))}
      </nldd-menu-bar>
    </div>
  );
}
