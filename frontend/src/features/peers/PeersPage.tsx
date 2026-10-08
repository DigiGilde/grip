import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth/context';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { ActionBar } from '@/ui/ActionBar';
import { Page, NoAccess } from '@/ui/layout';
import { OpenCell, OpenRow } from '@/ui/RowActions';
import { EmptyRows, QueryState } from '@/features/team/ui/states';
import { PEERS_KEY, ROLE_LABELS, fetchPeers, type Peer } from './api';
import { PeerSheet } from './PeerSheet';

function grantSummary(peer: Peer, services: string[]): string {
  const recorded = services.filter((service) => peer.grant_hashes[service]);
  if (recorded.length === 0) return 'Geen grant hash vastgelegd';
  return recorded.join(', ');
}

/**
 * The other instances and corpus systems this instance talks to. For the
 * beheerder: without a row here nothing is accepted from a party and nothing
 * is sent to it.
 */
export function PeersPage() {
  const instance = useInstance();
  const { state } = useAuth();
  const isAdmin = state.status === 'authenticated' && state.functions.includes('beheerder');
  const query = useQuery({ queryKey: PEERS_KEY, queryFn: fetchPeers, enabled: isAdmin });
  const peers = query.data?.items ?? [];
  const services = query.data?.services ?? [];
  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const opened = peers.find((peer) => peer.id === openId) ?? null;

  return (
    <>
      <Page
        title="Koppelingen"
        instanceName={instance?.name}
        back={{ href: PATHS.admin, text: 'Terug naar Beheer' }}
      >
        {/* Only once the list is there: who may not read it may not add to it. */}
        {query.isSuccess ? (
          <ActionBar
            label="Koppelingen"
            filters={[]}
            actions={[{ text: 'Nieuwe koppeling', onClick: () => setAdding(true), primary: true }]}
          />
        ) : null}
        {isAdmin ? null : (
          <NoAccess who="Koppelingen zijn voor beheerders. Wie dat zijn zie je onder Team." />
        )}
        {isAdmin ? (
          <QueryState query={query}>
            {query.data && !query.data.outway_configured ? (
              <nldd-banner
                variant="warning"
                size="sm"
                text="Er is geen outway ingesteld"
                supporting-text="Berichten naar andere organisaties blijven in de wachtrij."
              />
            ) : null}
            <nldd-table
              accessible-label="Koppelingen met andere instanties en corpus-systemen"
              columns="minmax(200px,2fr) minmax(160px,1fr) minmax(200px,2fr)"
              sm-columns="minmax(0,1fr)"
            >
              <nldd-table-row slot="header">
                <nldd-text-cell text="Naam" />
                <nldd-text-cell text="Soort" hide-below="md" />
                <nldd-text-cell text="Contract voor" hide-below="md" />
              </nldd-table-row>
              {peers.map((peer) => (
                <OpenRow key={peer.id} onOpen={() => setOpenId(peer.id)}>
                  <OpenCell
                    text={peer.name}
                    supportingText={peer.base_uri}
                    accessibleLabel={`Bekijk ${peer.name}`}
                    onOpen={() => setOpenId(peer.id)}
                  >
                    {peer.is_active ? null : <nldd-badge color="neutral" text="Uitgeschakeld" />}
                  </OpenCell>
                  <nldd-text-cell
                    hide-below="md"
                    text={ROLE_LABELS[peer.role]}
                    {...(peer.financial_inspection
                      ? { 'supporting-text': 'Met financiële inzage' }
                      : {})}
                  />
                  <nldd-text-cell
                    hide-below="md"
                    text={grantSummary(peer, services)}
                    supporting-text={`Peer-id ${peer.peer_id}`}
                  />
                </OpenRow>
              ))}
              <EmptyRows
                text="Nog geen koppelingen"
                supportingText="Voeg een instantie of een corpus toe zodra er een FSC-contract mee is."
              />
            </nldd-table>
          </QueryState>
        ) : null}
      </Page>

      <PeerSheet
        open={adding || opened !== null}
        peer={adding ? null : opened}
        services={services}
        onClose={() => {
          setAdding(false);
          setOpenId(null);
        }}
      />
    </>
  );
}
