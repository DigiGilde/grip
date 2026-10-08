import { Outlet } from 'react-router-dom';
import { useAuth } from '@/auth/context';
import { Button } from '@/features/assignments/ui';
import { useInstance } from '@/layout/useInstance';
import { useRouteFocus } from '@/layout/useRouteFocus';

const MAIN_CONTENT_ID = 'inhoud';

/**
 * The frame around the signing pages. Deliberately not the application
 * shell: an invited signer has one thing to do here, so there is no
 * navigation to screens they cannot open, only the way out.
 */
export function SigningLayout() {
  const instance = useInstance();
  const { logout, state } = useAuth();
  // Who is signing: a guest has no account menu to see it in.
  const signerName =
    state.status === 'guest'
      ? state.guest.name
      : state.status === 'authenticated'
        ? state.person.name
        : null;
  useRouteFocus();
  const instanceName = instance?.name ?? 'Grip';

  return (
    <>
      <nldd-skip-link href={`#${MAIN_CONTENT_ID}`} text="Direct naar de inhoud" />
      <nldd-app-view>
        <nldd-page landmarks="page" accessible-label={`Tekenen bij ${instanceName}`}>
          <nldd-container padding="16" layout="wrap" gap="16" vertical-alignment="center">
            <nldd-text>{instanceName}</nldd-text>
            {signerName && <nldd-text>Ingelogd als {signerName}</nldd-text>}
            <Button text="Uitloggen" size="sm" onClick={logout} />
          </nldd-container>
          <div id={MAIN_CONTENT_ID} tabIndex={-1}>
            <Outlet />
          </div>
        </nldd-page>
      </nldd-app-view>
    </>
  );
}
