/**
 * The tabs of one open thing (an assignment, a vacancy): each tab a page with
 * its own address. On a wide screen the design system's tab bar; on a narrow
 * one the same choice as one select, because a tab bar that does not fit
 * cuts its labels down to a letter.
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
  // Each tab is a page with its own address, so this is navigation: the
  // design system then renders a nav landmark and marks the current page.
  return (
    <nldd-tab-bar ref={ref} navigation accessible-label={label}>
      {items.map((item) => (
        <nldd-tab-bar-item
          key={item.key}
          href={item.href}
          text={item.text}
          current={orUndef(item.key === current)}
        />
      ))}
    </nldd-tab-bar>
  );
}
