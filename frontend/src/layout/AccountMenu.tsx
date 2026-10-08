import { useRef } from 'react';
import { useNlddEvent } from '@/components/nldd/events';
import { useAuth } from '@/auth/context';
import { PATHS } from '@/paths';
import { install, useCanInstall } from '@/pwa/install';
import { ICONS } from '@/ui/icons';
import { DevPersonSwitch, useViewingAs } from './DevPersonSwitch';
import { useInstance } from './useInstance';
import { useRouterLinks } from './useRouterLinks';
import { useViewer, viewerWords } from './useViewer';

interface LogoutItemProps {
  slot?: string;
}

/** "Uitloggen" as a menu item; `select` does not reach React's own handlers. */
export function LogoutMenuItem({ slot }: LogoutItemProps) {
  const { logout } = useAuth();
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', logout);
  return <nldd-menu-item ref={ref} {...(slot ? { slot } : {})} icon="logout" text="Uitloggen" />;
}

/** "Installeer grip", only while the browser offers to install it. */
function InstallMenuItem() {
  const canInstall = useCanInstall();
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', () => void install());
  if (!canInstall) return null;
  return <nldd-menu-item ref={ref} icon={ICONS.download.icon} text="Installeer grip" />;
}

interface AccountMenuProps {
  /** Where the menu opens: below the button in a top bar, above it in a bottom bar. */
  placement: 'bottom-end' | 'top-end';
  /** Icon only, for the bottom bar of a small screen where a name does not fit. */
  compact?: boolean;
}

/**
 * Who you are, in the bar: your name on the button, and behind it as what you
 * look at grip, your own page and the way out.
 *
 * In local development the button also says when you look as an example
 * person, and the menu lets you choose one.
 */
export function AccountMenu({ placement, compact }: AccountMenuProps) {
  const viewer = useViewer();
  const instance = useInstance();
  const viewingAs = useViewingAs();
  const ref = useRef<HTMLElement>(null);
  useRouterLinks(ref);
  const person = viewer.person;
  const name = person?.name ?? 'Account';
  const words = person ? viewerWords(viewer) : '';

  const menu = (
    <nldd-menu ref={ref} slot="popup" placement={placement}>
      {person && (
        <nldd-container slot="header" padding="16">
          <nldd-identity
            text={person.name}
            supporting-text={[words, instance?.name].filter(Boolean).join(' · ')}
          />
        </nldd-container>
      )}
      {person && (
        <nldd-menu-item
          icon="person"
          text="Mijn gegevens"
          href={PATHS.teamPerson.replace(':personId', person.id)}
        />
      )}
      {person && (
        <nldd-menu-item icon={ICONS.notify.icon} text="Meldingen" href={PATHS.notifications} />
      )}
      {person && (
        <nldd-menu-item icon={ICONS.security.icon} text="Beveiliging" href={PATHS.security} />
      )}
      <InstallMenuItem />
      <LogoutMenuItem />
      <DevPersonSwitch currentId={person?.id ?? null} />
    </nldd-menu>
  );

  if (compact) {
    return (
      <nldd-icon-button icon="person-circle" text={name} expandable>
        {menu}
      </nldd-icon-button>
    );
  }
  return (
    <nldd-button
      appearance="neutral-transparent"
      start-icon="person-circle"
      text={name}
      {...(viewingAs ? { 'supporting-text': 'Bekijk als, alleen lokaal' } : {})}
      horizontal-alignment="left"
      max-width="280px"
      single-line
      expandable
    >
      {menu}
    </nldd-button>
  );
}
