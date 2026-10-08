import { useAuth } from '@/auth/context';
import { PATHS } from '@/paths';

export const TO_START = { href: PATHS.statusOverview, text: 'Terug naar Start' };
const TO_ADMIN = { href: PATHS.admin, text: 'Terug naar Beheer' };

/**
 * Where a page under Beheer leads back to: Beheer for who has it, Start for
 * anyone else, so the link never names a page the reader cannot open.
 */
export function useAdminBack(): { href: string; text: string } {
  const { state } = useAuth();
  const isAdmin = state.status === 'authenticated' && state.functions.includes('beheerder');
  return isAdmin ? TO_ADMIN : TO_START;
}
