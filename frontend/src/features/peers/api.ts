import { apiGet, apiPatch, apiPost } from '@/api/client';

export type PeerRole = 'counterpart' | 'parent' | 'child' | 'corpus';

export interface Peer {
  id: string;
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
  is_active: boolean;
  key_count: number;
  jwks_fetched_at: string | null;
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
  is_active: boolean;
}

export interface ConnectionTest {
  ok: boolean;
  detail: string;
  status_code: number | null;
  key_count: number;
}

export const PEERS_KEY = ['peers'] as const;

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

export function updatePeer(id: string, body: Partial<Omit<PeerInput, 'peer_id'>>): Promise<Peer> {
  return apiPatch<Peer>(`/api/peers/${id}`, body);
}

export function testConnection(id: string): Promise<ConnectionTest> {
  return apiPost<ConnectionTest>(`/api/peers/${id}/test-connection`, {});
}
