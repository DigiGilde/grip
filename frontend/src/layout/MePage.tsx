import { useAuth } from '@/auth/context';
import { PATHS } from '@/paths';
import { useCanInstall } from '@/pwa/install';
import { Button } from '@/ui/Button';
import { LinkRows } from '@/ui/LinkRows';
import { Page } from '@/ui/layout';
import { InstallMenuItem } from './AccountMenu';
import { DevPersonSwitch, useCanSwitchDevPerson } from './DevPersonSwitch';
import { ExamplePersonSwitch, useCanSwitchExamplePerson } from './ExampleMode';
import { useInstance } from './useInstance';
import { useViewer } from './useViewer';

/** What exists only here and now: installing, and looking as someone else. */
function MoreMenu({ currentId }: { currentId: string | null }) {
  const canInstall = useCanInstall();
  const canSwitchDev = useCanSwitchDevPerson();
  const canSwitchExample = useCanSwitchExamplePerson();
  if (!canInstall && !canSwitchDev && !canSwitchExample) return null;
  return (
    <nldd-button appearance="secondary" text="Meer" expandable>
      <nldd-menu slot="popup" placement="bottom-start">
        <InstallMenuItem />
        <DevPersonSwitch currentId={currentId} />
        <ExamplePersonSwitch />
      </nldd-menu>
    </nldd-button>
  );
}

/** The account as a page: your own details and settings, and the way out. */
export function MePage() {
  const { logout } = useAuth();
  const instance = useInstance();
  const person = useViewer().person;
  return (
    <Page kind="list" title="Ik" instanceName={instance?.name}>
      {person && (
        <LinkRows
          label="Mijn account"
          rows={[
            {
              key: 'details',
              text: 'Mijn gegevens',
              href: PATHS.person.replace(':personId', person.id),
            },
            { key: 'notifications', text: 'Meldingen instellen', href: PATHS.notifications },
            { key: 'security', text: 'Beveiliging', href: PATHS.security },
          ]}
        />
      )}
      <nldd-container layout="row" gap="8">
        <Button text="Uitloggen" onClick={logout} />
        <MoreMenu currentId={person?.id ?? null} />
      </nldd-container>
    </Page>
  );
}
