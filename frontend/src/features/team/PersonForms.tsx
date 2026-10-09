import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatDate } from '@/lib/format';
import { impactSentences } from '@/features/rates/impact';
import { RolePicker } from '@/features/roles';
import {
  FUNCTIONS,
  ROLE_SOURCE_LABELS,
  addHire,
  addScale,
  fetchPeople,
  peopleKey,
  previewScale,
  scalePreviewKey,
  setFunction,
  setKpiTarget,
  targetKey,
  setPersonRoles,
  updatePerson,
  type Kpi,
  type Person,
  type PersonRole,
} from './api';
import { CheckboxField, DateField, SelectField, TextField } from './ui/controls';
import { eurosToCents, percentInput } from './ui/money';
import { ConfirmDialog, Form } from './ui/overlays';
import { useSave } from './useSave';

/**
 * The forms of the person page, one per thing that can change about a
 * person. Each lives in a sheet the page opens; none is open by default and
 * each validates on submit.
 */

export function HireForm({
  person,
  day,
  onDone,
}: {
  person: Person;
  day: string;
  onDone: () => void;
}) {
  const save = useSave(onDone, { key: person.id, version: person.version });
  const [supplier, setSupplier] = useState('');
  const [cost, setCost] = useState('');
  const [from, setFrom] = useState(day);
  const [to, setTo] = useState('');
  const [reference, setReference] = useState('');
  return (
    <Form
      submitText="Leg inhuur vast"
      submitting={save.pending}
      error={save.error}
      conflict={save.conflict}
      onSubmit={() => {
        const cents = eurosToCents(cost);
        if (!supplier.trim() || !from || cents === null || cents < 0) {
          save.setError('Vul een leverancier, een ingangsdatum en een kostprijs in euro in.');
          return;
        }
        save.run((headers) =>
          addHire(
            person.id,
            {
              supplier,
              cost_monthly_rate_cents: cents,
              valid_from: from,
              valid_to: to || null,
              contract_reference: reference || null,
            },
            headers,
          ),
        );
      }}
    >
      <TextField
        label="Leverancier"
        supportingLabel="De partij via wie deze persoon wordt ingehuurd"
        value={supplier}
        onChange={setSupplier}
        required
      />
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
  );
}

/**
 * Record a scale from any date, in the past or the future. Before saving,
 * the sheet says what that changes from the date and which naverrekening it
 * causes for months that were already delivered.
 */
export function ScaleForm({
  person,
  day,
  onDone,
}: {
  person: Person;
  day: string;
  onDone: () => void;
}) {
  const save = useSave(onDone, { key: person.id, version: person.version });
  const [from, setFrom] = useState(day);
  const [scale, setScale] = useState('');
  const number = /^\d+$/.test(scale.trim()) ? Number.parseInt(scale, 10) : null;
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(from) && number !== null && number >= 1 && number <= 30;
  const impact = useQuery({
    queryKey: scalePreviewKey(person.id, from, number ?? 0),
    queryFn: () =>
      previewScale(person.id, {
        valid_from: from,
        billing_scale: number as number,
      }),
    enabled: valid,
    retry: false,
  });
  const sameStart = (person.scales ?? []).some((entry) => entry.valid_from === from);
  return (
    <Form
      submitText="Leg schaal vast"
      submitting={save.pending}
      error={save.error}
      conflict={save.conflict}
      onSubmit={() => {
        if (!valid || number === null) {
          save.setError('Vul een begindatum en een schaal van 1 tot en met 30 in.');
          return;
        }
        save.run((headers) =>
          addScale(person.id, { valid_from: from, billing_scale: number }, headers),
        );
      }}
    >
      <DateField label="Vanaf" value={from} onChange={setFrom} required />
      <TextField label="Schaal" value={scale} onChange={setScale} keyboard="numeric" required />
      <nldd-container gap="8">
        <nldd-title size={5} text="Dit verandert er" heading-level={2} />
        {!valid ? (
          <nldd-text size="sm" color="secondary">
            Vul een datum en een schaal in om te zien wat er verandert.
          </nldd-text>
        ) : impact.isPending ? (
          <nldd-inline-dialog variant="loading" text="Bezig met narekenen wat er verandert" />
        ) : impact.isError ? (
          <nldd-banner variant="critical" size="sm" text={errorMessage(impact.error)} />
        ) : (
          <>
            {sameStart ? (
              <nldd-text>
                Op {formatDate(from)} begint al een periode; die wordt verbeterd naar schaal{' '}
                {number}.
              </nldd-text>
            ) : null}
            {impactSentences(impact.data, from).map((sentence) => (
              <nldd-text key={sentence}>{sentence}</nldd-text>
            ))}
          </>
        )}
      </nldd-container>
    </Form>
  );
}

export function RolesForm({
  person,
  roles,
  onDone,
}: {
  person: Person;
  roles: PersonRole[];
  onDone: () => void;
}) {
  const save = useSave(onDone, { key: person.id, version: person.version });
  const [kept, setKept] = useState<{ id: string; name: string; source?: PersonRole['source'] }[]>(
    roles.map((role) => ({
      id: role.role_id,
      name: role.name,
      source: role.source,
    })),
  );
  const [removed, setRemoved] = useState<string[]>([]);
  const ids = kept.filter((role) => !removed.includes(role.id)).map((role) => role.id);
  return (
    <Form
      submitText="Bewaar rollen"
      submitting={save.pending}
      error={save.error}
      conflict={save.conflict}
      onSubmit={() => save.run((headers) => setPersonRoles(person.id, ids, headers))}
    >
      {kept.map((role) => (
        <CheckboxField
          key={role.id}
          label={
            role.source
              ? `${role.name} (${ROLE_SOURCE_LABELS[role.source].toLowerCase()})`
              : role.name
          }
          checked={!removed.includes(role.id)}
          onChange={(checked) =>
            setRemoved((old) => (checked ? old.filter((id) => id !== role.id) : [...old, role.id]))
          }
        />
      ))}
      <RolePicker
        label="Rol toevoegen"
        supportingLabel="Een rol die je hier toevoegt, staat als met de hand toegekend"
        optional
        value={null}
        exclude={kept.map((role) => role.id)}
        onChange={(role) => {
          if (role && !kept.some((k) => k.id === role.id)) {
            setKept((old) => [...old, { id: role.id, name: role.name }]);
          }
        }}
      />
    </Form>
  );
}

export function TargetForm({
  person,
  year,
  kpi,
  onDone,
}: {
  person: Person;
  year: number;
  kpi: Kpi | null;
  onDone: () => void;
}) {
  const save = useSave(onDone, {
    key: targetKey(person.id, year),
    version: kpi?.target_version,
  });
  const [value, setValue] = useState(
    kpi?.target_pct ? String(Number(kpi.target_pct)).replace('.', ',') : '',
  );
  return (
    <Form
      submitText="Bewaar target"
      submitting={save.pending}
      error={save.error}
      conflict={save.conflict}
      onSubmit={() => {
        const pct = percentInput(value);
        if (pct === null || Number(pct) > 100) {
          save.setError('Vul een percentage van 0 tot en met 100 in.');
          return;
        }
        save.run((headers) => setKpiTarget(person.id, year, pct, headers));
      }}
    >
      <TextField
        label="Target declarabel"
        supportingLabel="Percentage van het jaar dat declarabel moet zijn"
        value={value}
        onChange={setValue}
        keyboard="decimal"
        required
      />
    </Form>
  );
}

export function GrantForm({ person, onDone }: { person: Person; onDone: () => void }) {
  const save = useSave(onDone);
  const held = (person.function_grants ?? []).map((g) => g.function);
  const available = FUNCTIONS.filter((fn) => !held.includes(fn.id));
  const [chosen, setChosen] = useState('');
  const [confirming, setConfirming] = useState(false);
  const right = available.find((fn) => fn.id === chosen) ?? null;
  const grant = () => {
    if (right) save.run(() => setFunction(person.id, right.id, true));
  };
  return (
    <>
      <Form
        submitText="Ken toe"
        submitting={save.pending}
        error={save.error}
        conflict={save.conflict}
        onSubmit={() => {
          if (!right) {
            save.setError('Kies het recht dat je wilt toekennen.');
            return;
          }
          // The two rights that reach far are confirmed first.
          if (right.farReaching) setConfirming(true);
          else grant();
        }}
      >
        <SelectField
          label="Recht"
          value={chosen}
          onChange={setChosen}
          emptyLabel="Kies een recht"
          options={available.map((fn) => ({ value: fn.id, label: fn.label }))}
        />
        <nldd-inline-dialog
          horizontal-alignment="left"
          text={
            right
              ? `${right.label}: ${right.description}`
              : 'Kies een recht om te zien wat het toestaat'
          }
          supporting-text="Het recht gaat in zodra je het toekent en komt met jouw naam in de auditlog."
        />
      </Form>
      <ConfirmDialog
        open={confirming}
        text={right ? `${person.name} het recht ${right.label} geven?` : ''}
        supportingText={
          right?.id === 'beheerder'
            ? `${person.name} kan daarna tarieven en personen beheren, rechten toekennen en intrekken, en gesloten jaren wijzigen.`
            : `${person.name} kan daarna offertes tekenen namens de organisatie; een getekende offerte bindt de organisatie.`
        }
        confirmText="Ken toe"
        onClose={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          grant();
        }}
      />
    </>
  );
}

/** Name and address: who this is. */
export function IdentityForm({ person, onDone }: { person: Person; onDone: () => void }) {
  const save = useSave(onDone, { key: person.id, version: person.version });
  const [name, setName] = useState(person.name);
  const [email, setEmail] = useState(person.email ?? '');
  return (
    <Form
      submitText="Bewaar gegevens"
      submitting={save.pending}
      error={save.error}
      conflict={save.conflict}
      onSubmit={() => {
        const address = email.trim();
        if (!name.trim() || (address !== '' && !address.includes('@'))) {
          save.setError('Vul een naam en een geldig e-mailadres in.');
          return;
        }
        save.run((headers) =>
          updatePerson(
            person.id,
            {
              name,
              // An empty address is left out: a prospective colleague has none yet.
              ...(address ? { email: address } : {}),
            },
            headers,
          ),
        );
      }}
    >
      <TextField label="Naam" value={name} onChange={setName} autocomplete="off" required />
      <TextField
        label="E-mailadres"
        {...(person.stage === 'prospective'
          ? {
              supportingLabel:
                'Komt uit Wies zodra het adres bestaat; daarna kan de persoon inloggen',
              optional: true,
            }
          : {})}
        value={email}
        onChange={setEmail}
        type="email"
        autocomplete="off"
      />
    </Form>
  );
}

/** A new line manager. */
export function ManagerForm({
  person,
  day,
  onDone,
}: {
  person: Person;
  day: string;
  onDone: () => void;
}) {
  const save = useSave(onDone, { key: person.id, version: person.version });
  const people = useQuery({
    queryKey: peopleKey(day, false),
    queryFn: () => fetchPeople(day, false),
  });
  const [managerId, setManagerId] = useState(person.manager_id ?? '');
  return (
    <Form
      submitText="Bewaar leidinggevende"
      submitting={save.pending}
      error={save.error}
      conflict={save.conflict}
      onSubmit={() =>
        save.run((headers) => updatePerson(person.id, { manager_id: managerId || null }, headers))
      }
    >
      <SelectField
        label="Leidinggevende"
        optional
        value={managerId}
        onChange={setManagerId}
        emptyLabel="Geen"
        options={(people.data?.items ?? [])
          .filter((p) => p.id !== person.id)
          .map((p) => ({ value: p.id, label: p.name }))}
      />
    </Form>
  );
}
