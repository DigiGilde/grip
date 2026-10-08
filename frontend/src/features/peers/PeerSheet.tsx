import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatDate } from '@/lib/format';
import { Button, SelectField, SwitchField, TextField } from '@/features/team/ui/controls';
import { Form, Sheet } from '@/features/team/ui/overlays';
import {
  PEERS_KEY,
  ROLE_LABELS,
  createPeer,
  testConnection,
  updatePeer,
  type ConnectionTest,
  type Peer,
  type PeerInput,
  type PeerRole,
} from './api';

interface PeerSheetProps {
  open: boolean;
  /** The peer to change; null to add one. */
  peer: Peer | null;
  services: string[];
  onClose: () => void;
}

const ROLE_OPTIONS = (Object.keys(ROLE_LABELS) as PeerRole[]).map((role) => ({
  value: role,
  label: ROLE_LABELS[role],
}));

/** Add a peer, or change one and test the connection with it. */
export function PeerSheet({ open, peer, services, onClose }: PeerSheetProps) {
  return (
    <Sheet
      open={open}
      title={peer ? peer.name : 'Koppeling toevoegen'}
      dismissText={peer ? 'Sluit' : 'Annuleer'}
      onClose={onClose}
      width="640px"
    >
      {open ? (
        <nldd-container gap="32">
          <PeerForm key={peer?.id ?? 'new'} peer={peer} services={services} onSaved={onClose} />
          {peer ? <Connection peer={peer} /> : null}
        </nldd-container>
      ) : null}
    </Sheet>
  );
}

interface PeerFormProps {
  peer: Peer | null;
  services: string[];
  onSaved: () => void;
}

function PeerForm({ peer, services, onSaved }: PeerFormProps) {
  const queryClient = useQueryClient();
  const [peerId, setPeerId] = useState(peer?.peer_id ?? '');
  const [name, setName] = useState(peer?.name ?? '');
  const [baseUri, setBaseUri] = useState(peer?.base_uri ?? '');
  const [tooiUri, setTooiUri] = useState(peer?.organisation_tooi_uri ?? '');
  const [role, setRole] = useState<PeerRole>(peer?.role ?? 'counterpart');
  const [grants, setGrants] = useState<Record<string, string>>(peer?.grant_hashes ?? {});
  const [financial, setFinancial] = useState(peer?.financial_inspection ?? false);
  const [active, setActive] = useState(peer?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (body: PeerInput) => {
      if (!peer) return createPeer(body);
      const { peer_id: _unchangeable, ...changes } = body;
      return updatePeer(peer.id, changes);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: PEERS_KEY });
      onSaved();
    },
    onError: (err) => setError(errorMessage(err)),
  });

  return (
    <Form
      submitText={peer ? 'Bewaar wijzigingen' : 'Voeg toe'}
      submitting={save.isPending}
      error={error}
      onSubmit={() => {
        if (!peerId.trim() || !name.trim() || !/^https?:\/\//.test(baseUri.trim())) {
          setError('Vul een peer-id, een naam en een basis-URI die met http begint in.');
          return;
        }
        save.mutate({
          peer_id: peerId.trim(),
          name: name.trim(),
          organisation_tooi_uri: tooiUri.trim(),
          base_uri: baseUri.trim(),
          role,
          grant_hashes: grants,
          financial_inspection: financial,
          is_active: active,
        });
      }}
    >
      {peer ? null : (
        <TextField
          label="Kenmerk in FSC (peer-id)"
          supportingLabel="Het serienummer uit het FSC-certificaat van de andere partij"
          value={peerId}
          onChange={setPeerId}
          required
        />
      )}
      <TextField label="Naam" value={name} onChange={setName} required />
      <SelectField
        label="Soort"
        supportingLabel="Bepaalt wat deze partij hier mag opvragen en sturen"
        value={role}
        onChange={(value) => setRole(value as PeerRole)}
        options={ROLE_OPTIONS}
      />
      <TextField
        label="Basis-URI"
        supportingLabel="Het begin van de URI's die deze partij uitgeeft"
        value={baseUri}
        onChange={setBaseUri}
        required
      />
      <TextField
        label="TOOI-URI van de organisatie"
        optional
        value={tooiUri}
        onChange={setTooiUri}
      />
      {services.map((service) => (
        <TextField
          key={service}
          label={`Grant hash voor ${service}`}
          supportingLabel="Uit het FSC-contract met deze partij"
          optional
          value={grants[service] ?? ''}
          onChange={(value) => setGrants({ ...grants, [service]: value })}
        />
      ))}
      {role === 'corpus' ? null : (
        <SwitchField
          label="Mag als opdrachtgever uitputting en factuurgegevens opvragen"
          checked={financial}
          onChange={setFinancial}
        />
      )}
      <SwitchField
        label="Actief: verkeer met deze partij is toegestaan"
        checked={active}
        onChange={setActive}
      />
    </Form>
  );
}

function Connection({ peer }: { peer: Peer }) {
  const queryClient = useQueryClient();
  const [result, setResult] = useState<ConnectionTest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const test = useMutation({
    mutationFn: () => testConnection(peer.id),
    onSuccess: async (outcome) => {
      setError(null);
      setResult(outcome);
      await queryClient.invalidateQueries({ queryKey: PEERS_KEY });
    },
    onError: (err) => {
      setResult(null);
      setError(errorMessage(err));
    },
  });
  const known =
    peer.key_count > 0
      ? `${peer.key_count} sleutel(s) bekend, opgehaald op ${formatDate(peer.jwks_fetched_at)}`
      : 'Nog geen sleutels van deze partij bekend';
  return (
    <nldd-container gap="8">
      <nldd-title
        size={4}
        text="Verbinding"
        heading-level={2}
        supporting-text={peer.role === 'corpus' ? 'Vraagt het corpus op via de outway' : known}
      />
      {result ? (
        <nldd-banner
          variant={result.ok ? 'success' : 'critical'}
          text={result.ok ? 'Verbinding in orde' : 'Geen verbinding'}
          supporting-text={result.detail}
        />
      ) : null}
      {error ? (
        <nldd-banner variant="critical" text="De test is niet uitgevoerd" supporting-text={error} />
      ) : null}
      <nldd-container layout="wrap" gap="8">
        <Button
          text="Test de verbinding"
          appearance="secondary"
          loading={test.isPending}
          onClick={() => test.mutate()}
        />
      </nldd-container>
    </nldd-container>
  );
}
