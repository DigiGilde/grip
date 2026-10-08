import { useRef } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/context';
import { useNlddEvent } from '@/components/nldd/events';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { PageHeading } from './PageHeading';
import { StatusPage } from './StatusPage';

/** Where to go after login: the page the guard sent the visitor away from. */
function returnPath(state: unknown): string {
  const from = (state as { from?: unknown } | null)?.from;
  return typeof from === 'string' && from.startsWith('/') ? from : PATHS.statusOverview;
}

export function LoginPage() {
  const { state, login } = useAuth();
  const location = useLocation();
  const instance = useInstance();
  const loginRef = useRef<HTMLElement>(null);
  useNlddEvent(loginRef, 'click', login);

  if (state.status === 'loading') {
    return <StatusPage variant="loading" title="Grip wordt geladen" />;
  }
  if (state.status === 'authenticated') {
    return <Navigate to={returnPath(location.state)} replace />;
  }
  if (state.status === 'no-access') {
    return <Navigate to={PATHS.noAccess} replace />;
  }

  const instanceName = instance?.name ?? 'Grip';
  const loginAvailable = state.status === 'unauthenticated' && state.oidcConfigured;

  return (
    <nldd-app-view background="tinted">
      <nldd-page landmarks="page">
        <nldd-simple-section width="400px" vertical-alignment="center">
          <nldd-container gap="24">
            <PageHeading text={`Inloggen bij ${instanceName}`} instanceName={instance?.name} />

            {state.status === 'error' && (
              <nldd-banner variant="critical" size="sm" text={state.message} />
            )}
            {state.status === 'unauthenticated' && !state.oidcConfigured && (
              <nldd-banner
                variant="warning"
                size="sm"
                text="Inloggen is op deze omgeving niet ingesteld."
                supporting-text="Neem contact op met de beheerder."
              />
            )}

            {loginAvailable && (
              <nldd-button
                ref={loginRef}
                appearance="primary"
                width="full"
                text="Inloggen met SSO Rijk"
              />
            )}
          </nldd-container>
        </nldd-simple-section>
      </nldd-page>
    </nldd-app-view>
  );
}
