import { apiGet, apiPatch, apiPost } from '@/api/client';
import type { RequestHeaders } from '@/api/client';

export type PeerRole = 'counterpart' | 'parent' | 'child' | 'corpus';

export interface Peer {
  id: string;
  version?: number;
  /** The FSC peer id: the serial number in the certificate of the peer. */
  peer_id: string;
  name: string;
  organisation_tooi_uri: string;
  /** Base of the URIs the peer mints: an instance base or a corpus base. */
  base_uri: string;
  role: PeerRole;
  /** FSC service name to the grant hash of the contract with this peer. */
  grant_hashes: Record<string, string>;
  financial_inspection: boolean;
  /** The peer is an example instance; only an example instance talks to it. */
  is_example: boolean;
  is_active: boolean;
  key_count: number;
  jwks_fetched_at: string | null;
  /** How many messages to this peer do not arrive. */
  undelivered: number;
}

/** A message to a peer that does not arrive. */
export interface UndeliveredMessage {
  id: string;
  /** What the message is, in words. */
  kind: string;
  /** Why it does not arrive, in words. */
  reason: string;
  since: string;
  /** Until when grip tries; absent when it does not, or has not started again. */
  retry_until: string | null;
  /** Refused for good, or tried for the whole window: only a person sends it again. */
  final: boolean;
}

export interface UndeliveredList {
  items: UndeliveredMessage[];
}

export interface PeerList {
  items: Peer[];
  services: string[];
  outway_configured: boolean;
}

export interface PeerInput {
  peer_id: string;
  name: string;
  organisation_tooi_uri: string;
  base_uri: string;
  role: PeerRole;
  grant_hashes: Record<string, string>;
  financial_inspection: boolean;
  is_example: boolean;
  is_active: boolean;
}

export interface ConnectionTest {
  ok: boolean;
  detail: string;
  status_code: number | null;
  key_count: number;
}

export const PEERS_KEY = ['peers'] as const;
export const undeliveredKey = (peerId: string) => [...PEERS_KEY, peerId, 'undelivered'] as const;

export const ROLE_LABELS: Record<PeerRole, string> = {
  counterpart: 'Opdrachtgever of opdrachtnemer',
  parent: 'Moederinstantie',
  child: 'Dochterinstantie',
  corpus: 'Corpus-systeem',
};

export function fetchPeers(): Promise<PeerList> {
  return apiGet<PeerList>('/api/peers');
}

export function createPeer(body: PeerInput): Promise<Peer> {
  return apiPost<Peer>('/api/peers', body);
}

export function updatePeer(
  id: string,
  body: Partial<Omit<PeerInput, 'peer_id'>>,
  headers?: RequestHeaders,
): Promise<Peer> {
  return apiPatch<Peer>(`/api/peers/${id}`, body, headers);
}

export function testConnection(id: string): Promise<ConnectionTest> {
  return apiPost<ConnectionTest>(`/api/peers/${id}/test-connection`, {});
}

export function fetchUndelivered(peerId: string): Promise<UndeliveredList> {
  return apiGet<UndeliveredList>(`/api/peers/${peerId}/undelivered`);
}

export function resendMessage(peerId: string, messageId: string): Promise<UndeliveredMessage> {
  return apiPost<UndeliveredMessage>(`/api/peers/${peerId}/undelivered/${messageId}/resend`, {});
}
