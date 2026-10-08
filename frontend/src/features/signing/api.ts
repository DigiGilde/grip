/** The signing-link endpoints: what an invited signer sees and sends. */
import { apiGet, apiPost } from '@/api/client';
import type { QuoteContent } from '@/features/quotes/api';

export interface SigningInvitation {
  quote_id: string;
  assignment_name: string;
  status: string;
  issued_at: string;
  valid_until?: string | null;
  expires_at: string | null;
}

export interface SigningQuote {
  id: string;
  uri: string;
  status: 'issued' | 'accepted' | 'rejected' | 'superseded' | string;
  issued_at: string;
  contractor_name: string;
  client_name: string | null;
  snapshot_hash: string;
  content: QuoteContent;
  decided_at: string | null;
}

export const signingKeys = {
  invitations: ['signing', 'invitations'] as const,
  quote: (quoteId: string) => ['signing', 'quote', quoteId] as const,
};

export function fetchSigningInvitations(): Promise<{ invitations: SigningInvitation[] }> {
  return apiGet('/api/signing/invitations');
}

export function fetchSigningQuote(quoteId: string): Promise<SigningQuote> {
  return apiGet(`/api/signing/quotes/${quoteId}`);
}

export function acceptQuote(
  quoteId: string,
  input: {
    quote_hash: string;
    signer_function: string | null;
    organisation_name: string | null;
    confirm_mandate: boolean;
  },
): Promise<SigningQuote> {
  return apiPost(`/api/signing/quotes/${quoteId}/accept`, input);
}

export function rejectQuote(
  quoteId: string,
  input: { quote_hash: string; reason: string | null },
): Promise<SigningQuote> {
  return apiPost(`/api/signing/quotes/${quoteId}/reject`, input);
}

export function signingDocumentUrl(quoteId: string, download = false): string {
  return `/api/signing/quotes/${quoteId}/document${download ? '?download=true' : ''}`;
}
