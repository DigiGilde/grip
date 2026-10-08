import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { Button } from '@/features/team/ui/controls';
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
  const query = useQuery({ queryKey: PEERS_KEY, queryFn: fetchPeers });
  const peers = query.data?.items ?? [];
  const services = query.data?.services ?? [];
  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const opened = peers.find((peer) => peer.id === openId) ?? null;

  return (
    <>
      <nldd-simple-section>
        <PageHeading text="Koppelingen" instanceName={instance?.name} />
        <nldd-container gap="16">
          <QueryState query={query}>
            {query.data && !query.data.outway_configured ? (
              <nldd-banner
                variant="warning"
                text="Er is geen outway ingesteld"
                supporting-text="Deze instantie kan nu niets naar andere organisaties sturen. Berichten blijven in de wachtrij staan."
              />
            ) : null}
            <nldd-container layout="wrap" gap="16">
              <Button text="Koppeling toevoegen" onClick={() => setAdding(true)} />
            </nldd-container>
            <nldd-table
              accessible-label="Koppelingen met andere instanties en corpus-systemen"
              columns="minmax(180px,2fr) minmax(160px,1fr) minmax(200px,2fr) 110px 110px"
            >
              <nldd-table-row slot="header">
                <nldd-text-cell text="Naam" />
                <nldd-text-cell text="Soort" />
                <nldd-text-cell text="Contract voor" />
                <nldd-text-cell text="Status" />
                <nldd-text-cell text="Actie" />
              </nldd-table-row>
              {peers.map((peer) => (
                <nldd-table-row key={peer.id}>
                  <nldd-text-cell text={peer.name} supporting-text={peer.base_uri} />
                  <nldd-text-cell
                    text={ROLE_LABELS[peer.role]}
                    {...(peer.financial_inspection
                      ? { 'supporting-text': 'Met financiële inzage' }
                      : {})}
                  />
                  <nldd-text-cell
                    text={grantSummary(peer, services)}
                    supporting-text={`Peer-id ${peer.peer_id}`}
                  />
                  <nldd-text-cell
                    text={peer.is_active ? 'Actief' : 'Uitgeschakeld'}
                    {...(peer.is_active ? {} : { color: 'critical' })}
                  />
                  <nldd-cell>
                    <Button
                      size="sm"
                      text="Bekijk"
                      accessibleLabel={`Bekijk ${peer.name}`}
                      onClick={() => setOpenId(peer.id)}
                    />
                  </nldd-cell>
                </nldd-table-row>
              ))}
              <EmptyRows
                text="Er zijn nog geen koppelingen"
                supportingText="Voeg de instantie van een opdrachtgever, een opdrachtnemer of een corpus-systeem toe zodra er een FSC-contract mee is."
              />
            </nldd-table>
          </QueryState>
        </nldd-container>
      </nldd-simple-section>

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
