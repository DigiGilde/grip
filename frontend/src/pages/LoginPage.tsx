import { useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Navigate, useLocation } from 'react-router-dom';
import { parseLoginError, safeReturnPath } from '@/api/auth';
import { errorMessage } from '@/api/client';
import { AUTH_STATUS_KEY } from '@/auth/authState';
import { useAuth } from '@/auth/context';
import {
  isCancellation,
  loginWithPasskey,
  passkeyMadeHere,
  passkeysSupported,
} from '@/features/passkeys/api';
import { Brand } from '@/brand/Brand';
import { instanceNames } from '@/brand/names';
import { ExampleNotice } from '@/layout/ExampleMode';
import { useNlddEvent } from '@/components/nldd/events';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { PageHeading } from './PageHeading';
import { StatusPage } from './StatusPage';

/** Where to go after login: the page the guard sent the visitor away from. */
function returnPath(state: unknown): string {
  const from = (state as { from?: unknown } | null)?.from;
  return safeReturnPath(from) ?? PATHS.statusOverview;
}

/** Set when the backend sent the visitor back after a login that failed. */
function loginFailed(state: unknown): boolean {
  const value = (state as { loginError?: unknown } | null)?.loginError;
  return parseLoginError(typeof value === 'string' ? value : null) === 'mislukt';
}

export function LoginPage() {
  const { state, login } = useAuth();
  const location = useLocation();
  const instance = useInstance();
  const loginRef = useRef<HTMLElement>(null);
  const passkeyRef = useRef<HTMLElement>(null);
  const queryClient = useQueryClient();
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [passkeyError, setPasskeyError] = useState<string | null>(null);
  const next = returnPath(location.state);
  useNlddEvent(loginRef, 'click', () => login(next));
  useNlddEvent(passkeyRef, 'click', () => {
    setPasskeyBusy(true);
    setPasskeyError(null);
    loginWithPasskey()
      // The session exists now; asking again who is logged in moves on.
      .then(() => queryClient.invalidateQueries({ queryKey: AUTH_STATUS_KEY }))
      .catch((failure: unknown) => {
        if (!isCancellation(failure)) setPasskeyError(errorMessage(failure));
      })
      .finally(() => setPasskeyBusy(false));
  });

  if (state.status === 'loading') {
    return <StatusPage variant="loading" title="Grip wordt geladen" />;
  }
  if (state.status === 'authenticated') {
    return <Navigate to={next} replace />;
  }
  if (state.status === 'no-access') {
    return <Navigate to={PATHS.noAccess} replace />;
  }
  if (state.status === 'guest') {
    return <Navigate to={PATHS.signing} replace />;
  }

  const { organisation } = instanceNames(instance?.name);
  const loginAvailable = state.status === 'unauthenticated' && state.oidcConfigured;
  // Offered only where it can work: the instance allows it, the browser can,
  // and a passkey was once made in this browser.
  const passkeyAvailable =
    state.status === 'unauthenticated' &&
    Boolean(state.passkeyLogin) &&
    passkeysSupported() &&
    passkeyMadeHere();

  return (
    <nldd-app-view background="tinted">
      <nldd-page landmarks="page">
        <nldd-simple-section width="400px" vertical-alignment="center">
          <nldd-container gap="24">
            <Brand variant="login" />
            <PageHeading
              text={organisation ? `Inloggen bij ${organisation}` : 'Inloggen'}
              instanceName={instance?.name}
              inline
            />

            <ExampleNotice />
            {loginFailed(location.state) && (
              <nldd-banner
                variant="critical"
                size="sm"
                text="Inloggen is mislukt."
                supporting-text="Probeer het opnieuw. Blijft het misgaan, neem dan contact op met de beheerder."
              />
            )}
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

            {passkeyError && <nldd-banner variant="critical" size="sm" text={passkeyError} />}

            {loginAvailable && (
              <nldd-button
                ref={loginRef}
                appearance="primary"
                width="full"
                text="Inloggen met SSO Rijk"
              />
            )}
            {passkeyAvailable && (
              <nldd-button
                ref={passkeyRef}
                appearance="secondary"
                width="full"
                text="Inloggen met passkey"
                {...(passkeyBusy ? { loading: true } : {})}
              />
            )}
          </nldd-container>
        </nldd-simple-section>
      </nldd-page>
    </nldd-app-view>
  );
}
