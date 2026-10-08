import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatEuro, formatPeriod } from '@/lib/format';
import {
  FUNCTIONS,
  addHire,
  addScale,
  fetchLoginState,
  functionLabel,
  loginKey,
  removeHire,
  setFunction,
  unbindLogin,
  updatePerson,
  type Person,
} from './api';
import {
  Button,
  CheckboxField,
  DateField,
  SelectField,
  SwitchField,
  TextField,
} from './ui/controls';
import { eurosToCents } from './ui/money';
import { Form, Sheet } from './ui/overlays';
import { EmptyRows } from './ui/states';

interface PersonSheetProps {
  person: Person | null;
  people: Person[];
  mayManage: boolean;
  /** The reference day of the list, used as the default start of a new period. */
  day: string;
  onClose: () => void;
}

/**
 * Everything the asker may see of one person, with the forms to change it
 * for whoever manages persons. A section the asker may not see is not drawn.
 */
export function PersonSheet({ person, people, mayManage, day, onClose }: PersonSheetProps) {
  return (
    <Sheet open={person !== null} title={person?.name ?? 'Persoon'} onClose={onClose} width="640px">
      {person ? (
        <PersonDetails
          key={person.id}
          person={person}
          people={people}
          mayManage={mayManage}
          day={day}
        />
      ) : null}
    </Sheet>
  );
}

function useSave() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ['team'] });
    },
    onError: (err) => setError(errorMessage(err)),
  });
  return { run: mutation.mutate, pending: mutation.isPending, error, setError };
}

type DetailsProps = Omit<PersonSheetProps, 'person' | 'onClose'> & { person: Person };

function PersonDetails({ person, people, mayManage, day }: DetailsProps) {
  return (
    <nldd-container gap="32">
      {mayManage ? (
        <IdentityForm person={person} people={people} />
      ) : (
        <nldd-title
          size={5}
          text={person.email}
          heading-level={2}
          supporting-text={
            person.manager_name ? `Leidinggevende: ${person.manager_name}` : 'Geen leidinggevende'
          }
        />
      )}
      {mayManage ? <Login person={person} /> : null}
      {'functions' in person ? <Functions person={person} mayManage={mayManage} /> : null}
      {'scales' in person ? <Scales person={person} mayManage={mayManage} day={day} /> : null}
      {'hires' in person ? <Hires person={person} mayManage={mayManage} day={day} /> : null}
    </nldd-container>
  );
}

function IdentityForm({ person, people }: { person: Person; people: Person[] }) {
  const save = useSave();
  const [name, setName] = useState(person.name);
  const [email, setEmail] = useState(person.email);
  const [managerId, setManagerId] = useState(person.manager_id ?? '');
  const [active, setActive] = useState(person.is_active);
  return (
    <nldd-container gap="8">
      <nldd-title size={4} text="Gegevens" heading-level={2} />
      <Form
        submitText="Bewaar gegevens"
        submitting={save.pending}
        error={save.error}
        onSubmit={() => {
          if (!name.trim() || !email.includes('@')) {
            save.setError('Vul een naam en een geldig e-mailadres in.');
            return;
          }
          save.run(() =>
            updatePerson(person.id, {
              name,
              email,
              manager_id: managerId || null,
              is_active: active,
            }),
          );
        }}
      >
        <TextField label="Naam" value={name} onChange={setName} autocomplete="off" required />
        <TextField
          label="E-mailadres"
          value={email}
          onChange={setEmail}
          type="email"
          autocomplete="off"
          required
        />
        <SelectField
          label="Leidinggevende"
          optional
          value={managerId}
          onChange={setManagerId}
          emptyLabel="Geen"
          options={people
            .filter((p) => p.id !== person.id)
            .map((p) => ({ value: p.id, label: p.name }))}
        />
        <SwitchField
          label="Actief: kan inloggen en worden ingezet"
          checked={active}
          onChange={setActive}
        />
      </Form>
    </nldd-container>
  );
}

/**
 * The login of a person, for the beheerder. A person is bound to an account
 * of the identity provider on the first login. When that account changes
 * (the provider was set up again, or the person got a new account there) the
 * login is refused until the binding is removed here.
 */
function Login({ person }: { person: Person }) {
  const save = useSave();
  const state = useQuery({
    queryKey: loginKey(person.id),
    queryFn: () => fetchLoginState(person.id),
    retry: false,
  });
  if (!state.data) return null;
  const bound = state.data.bound;
  return (
    <nldd-container gap="8">
      <nldd-title
        size={4}
        text="Inloggen"
        heading-level={2}
        supporting-text={
          bound
            ? 'Gekoppeld aan een account bij de identiteitsprovider'
            : 'Nog niet ingelogd; de eerste keer inloggen koppelt het account'
        }
      />
      {save.error ? <nldd-banner variant="critical" text={save.error} /> : null}
      {bound ? (
        <>
          <nldd-text size="sm" color="secondary">
            Kan deze persoon niet meer inloggen omdat het account bij de identiteitsprovider is
            vervangen? Ontkoppel dan de login. De volgende keer inloggen met hetzelfde e-mailadres
            koppelt het nieuwe account.
          </nldd-text>
          <div>
            <Button
              text="Ontkoppel login"
              accessibleLabel={`Ontkoppel de login van ${person.name}`}
              loading={save.pending}
              onClick={() => save.run(() => unbindLogin(person.id))}
            />
          </div>
        </>
      ) : null}
    </nldd-container>
  );
}

function Functions({ person, mayManage }: { person: Person; mayManage: boolean }) {
  const save = useSave();
  const held = person.functions ?? [];
  return (
    <nldd-container gap="8">
      <nldd-title
        size={4}
        text="Functies"
        heading-level={2}
        supporting-text={
          mayManage ? 'Een wijziging gaat direct in' : 'Wat deze persoon in de instantie mag'
        }
      />
      {save.error ? <nldd-banner variant="critical" text={save.error} /> : null}
      {mayManage ? (
        FUNCTIONS.map((fn) => (
          <CheckboxField
            key={fn.id}
            label={`${fn.label}: ${fn.description}`}
            checked={held.includes(fn.id)}
            disabled={save.pending}
            onChange={(checked) => save.run(() => setFunction(person.id, fn.id, checked))}
          />
        ))
      ) : (
        <nldd-text-cell text={held.length ? held.map(functionLabel).join(', ') : 'Geen functies'} />
      )}
    </nldd-container>
  );
}

function Scales({ person, mayManage, day }: { person: Person; mayManage: boolean; day: string }) {
  const save = useSave();
  const [from, setFrom] = useState(day);
  const [scale, setScale] = useState('');
  const scales = person.scales ?? [];
  return (
    <nldd-container gap="8">
      <nldd-title
        size={4}
        text="Inzetschaal"
        heading-level={2}
        supporting-text="De schaal waartegen deze persoon wordt gedeclareerd"
      />
      <nldd-table accessible-label={`Inzetschalen van ${person.name}`} columns="1fr 100px">
        <nldd-table-row slot="header">
          <nldd-text-cell text="Periode" />
          <nldd-text-cell text="Schaal" />
        </nldd-table-row>
        {scales.map((entry) => (
          <nldd-table-row key={entry.id}>
            <nldd-text-cell text={formatPeriod(entry.valid_from, entry.valid_to)} />
            <nldd-text-cell text={String(entry.billing_scale)} />
          </nldd-table-row>
        ))}
        <EmptyRows text="Er is nog geen inzetschaal vastgelegd" />
      </nldd-table>
      {mayManage ? (
        <Form
          submitText="Leg schaal vast"
          submitting={save.pending}
          error={save.error}
          onSubmit={() => {
            const number = Number.parseInt(scale, 10);
            if (!from || !/^\d+$/.test(scale.trim()) || number < 1 || number > 30) {
              save.setError('Vul een ingangsdatum en een schaal van 1 tot en met 30 in.');
              return;
            }
            save.run(async () => {
              await addScale(person.id, { valid_from: from, billing_scale: number });
              setScale('');
            });
          }}
        >
          <DateField
            label="Nieuwe schaal vanaf"
            supportingLabel="De vorige periode eindigt de dag ervoor"
            value={from}
            onChange={setFrom}
            required
          />
          <TextField label="Schaal" value={scale} onChange={setScale} keyboard="numeric" required />
        </Form>
      ) : null}
    </nldd-container>
  );
}

function Hires({ person, mayManage, day }: { person: Person; mayManage: boolean; day: string }) {
  const save = useSave();
  const [supplier, setSupplier] = useState('');
  const [cost, setCost] = useState('');
  const [from, setFrom] = useState(day);
  const [to, setTo] = useState('');
  const [reference, setReference] = useState('');
  const hires = person.hires ?? [];
  return (
    <nldd-container gap="8">
      <nldd-title
        size={4}
        text="Inhuur"
        heading-level={2}
        supporting-text={
          typeof person.margin_monthly_cents === 'number'
            ? `Marge op de peildatum: ${formatEuro(person.margin_monthly_cents)} per maand per FTE`
            : 'Kostprijs per FTE per maand'
        }
      />
      <nldd-table
        accessible-label={`Inhuur van ${person.name}`}
        columns={
          mayManage
            ? 'minmax(140px,1fr) minmax(140px,1fr) 120px 110px'
            : 'minmax(140px,1fr) minmax(140px,1fr) 120px'
        }
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Leverancier" />
          <nldd-text-cell text="Periode" />
          <nldd-text-cell text="Kostprijs" horizontal-alignment="right" />
          {mayManage ? <nldd-text-cell text="Actie" /> : null}
        </nldd-table-row>
        {hires.map((hire) => (
          <nldd-table-row key={hire.id}>
            <nldd-text-cell
              text={hire.supplier}
              {...(hire.contract_reference ? { 'supporting-text': hire.contract_reference } : {})}
            />
            <nldd-text-cell text={formatPeriod(hire.valid_from, hire.valid_to)} />
            <nldd-text-cell
              text={formatEuro(hire.cost_monthly_rate_cents)}
              horizontal-alignment="right"
            />
            {mayManage ? (
              <nldd-cell>
                <Button
                  size="sm"
                  text="Verwijder"
                  accessibleLabel={`Verwijder de inhuur via ${hire.supplier}`}
                  disabled={save.pending}
                  onClick={() => save.run(() => removeHire(person.id, hire.id))}
                />
              </nldd-cell>
            ) : null}
          </nldd-table-row>
        ))}
        <EmptyRows text="Deze persoon is niet ingehuurd" />
      </nldd-table>
      {mayManage ? (
        <Form
          submitText="Leg inhuur vast"
          submitting={save.pending}
          error={save.error}
          onSubmit={() => {
            const cents = eurosToCents(cost);
            if (!supplier.trim() || !from || cents === null || cents < 0) {
              save.setError('Vul een leverancier, een ingangsdatum en een kostprijs in euro in.');
              return;
            }
            save.run(async () => {
              await addHire(person.id, {
                supplier,
                cost_monthly_rate_cents: cents,
                valid_from: from,
                valid_to: to || null,
                contract_reference: reference || null,
              });
              setSupplier('');
              setCost('');
              setReference('');
            });
          }}
        >
          <TextField label="Leverancier" value={supplier} onChange={setSupplier} required />
          <TextField
            label="Kostprijs per FTE per maand"
            supportingLabel="In euro"
            value={cost}
            onChange={setCost}
            keyboard="decimal"
            required
          />
          <DateField label="Vanaf" value={from} onChange={setFrom} required />
          <DateField label="Tot en met" optional value={to} onChange={setTo} />
          <TextField label="Contractkenmerk" optional value={reference} onChange={setReference} />
        </Form>
      ) : null}
    </nldd-container>
  );
}
