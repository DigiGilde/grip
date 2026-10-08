import { useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { orUndef } from '@/components/nldd/events';
import { APP_ROUTES, isCurrentRoute } from '@/routes';
import { useRouterLinks } from './useRouterLinks';

interface MainNavigationProps {
  /** Icons with the label underneath, for the bottom bar on small screens. */
  withIcons?: boolean;
}

/** The sections of the application as tabs, for the main toolbar. */
export function MainNavigation({ withIcons }: MainNavigationProps) {
  const ref = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  useRouterLinks(ref);

  return (
    <nldd-tab-bar ref={ref} navigation accessible-label="Hoofdnavigatie">
      {APP_ROUTES.map((route) => (
        <nldd-tab-bar-item
          key={route.path}
          href={route.path}
          text={route.title}
          {...(withIcons ? { icon: route.icon } : {})}
          current={orUndef(isCurrentRoute(route.path, pathname))}
        />
      ))}
    </nldd-tab-bar>
  );
}

/** The same sections for the toolbar's overflow menu, where the tabs go when they do not fit. */
export function MainNavigationOverflow() {
  const ref = useRef<HTMLElement>(null);
  useRouterLinks(ref);

  return (
    <nldd-menu-group ref={ref} slot="overflow" text="Hoofdnavigatie">
      {APP_ROUTES.map((route) => (
        <nldd-menu-item key={route.path} href={route.path} icon={route.icon} text={route.title} />
      ))}
    </nldd-menu-group>
  );
}
