/**
 * A page under Beheer that only a beheerder has.
 *
 * The server refuses the data to anyone else; this says so before the page
 * asks for it, so nobody else sees the page's actions or a spinner that waits
 * for a refusal. Whether someone is a beheerder comes from the server too
 * (the rights in the login state).
 */
import type { ReactNode } from 'react';
import { useAuth } from '@/auth/context';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { NoAccess, Page } from '@/ui/layout';

export const FOR_BEHEERDERS = 'Beheer is voor beheerders. Wie dat zijn zie je onder Team.';

export function AdminOnly({ title, children }: { title: string; children: ReactNode }) {
  const { state } = useAuth();
  const instance = useInstance();
  if (state.status === 'authenticated' && state.functions.includes('beheerder')) {
    return <>{children}</>;
  }
  return (
    <Page
      title={title}
      instanceName={instance?.name}
      back={{ href: PATHS.statusOverview, text: 'Terug naar Start' }}
    >
      <NoAccess who={FOR_BEHEERDERS} />
    </Page>
  );
}
