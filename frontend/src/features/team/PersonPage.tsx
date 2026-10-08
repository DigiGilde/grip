import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { useAuth } from '@/auth/context';
import { formatDate, formatEuro, formatPercent, formatPeriod } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import {
  ENGAGEMENT_LABELS,
  FUNCTIONS,
  addHire,
  addScale,
  currentHire,
  engagementOf,
  fetchLoginState,
  fetchPeople,
  fetchPerson,
  fetchPersonKpi,
  functionLabel,
  loginKey,
  peopleKey,
  personKey,
  personKpiKey,
  removeHire,
  setFunction,
  setKpiTarget,
  today,
  unbindLogin,
  updatePerson,
  type FunctionGrant,
  type Hire,
  type Kpi,
  type Person,
} from './api';
import { Button, DateField, SelectField, SwitchField, TextField } from './ui/controls';
import { eurosToCents, percentInput } from './ui/money';
import { ConfirmDialog, Form, Sheet } from './ui/overlays';
import { Fact, Facts, Section } from './ui/section';
import { QueryState } from './ui/states';

/**
 * A person: who this is and how they are engaged, what they work on, and,
 * for who may see it, what they bill at, what they cost and their KPI. Rights
 * in grip and the login come last, for the beheerder.
 *
 * A page of its own rather than a side sheet: it holds up to six parts, and a
 * page can be linked to (from the Inzet board, from a vacancy). Nothing that
 * adds or changes is open by default: a section shows what is, its one
 * action opens the fields in a sheet, and the sheet validates on submit.
 *
 * A part the reader may not see is not rendered at all: the response does
 * not carry its fields, and the page draws a section only for fields that
 * are there.
 */
export function PersonPage() {
  const { personId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const requested = searchParams.get('peildatum');
  const day = requested && /^\d{4}-\d{2}-\d{2}$/.test(requested) ? requested : today();
  const instance = useInstance();
  const { state } = useAuth();
  const mayManage = state.status === 'authenticated' && state.functions.includes('beheerder');
  const backRef = useRef<HTMLDivElement>(null);
  useRouterLinks(backRef);

  const query = useQuery({
    queryKey: personKey(personId, day),
    queryFn: () => fetchPerson(personId, day),
    retry: false,
  });
  const person = query.data;
  const notFound = query.error instanceof ApiError && query.error.status === 404;

  return (
    <nldd-simple-section>
      <PageHeading text={person?.name ?? 'Persoon'} instanceName={instance?.name} />
      <div ref={backRef}>
        <nldd-link size="sm" href={PATHS.team} text="Terug naar Team" start-icon="arrow-left" />
      </div>
      {notFound ? (
        <nldd-inline-dialog
          text="Deze persoon is niet gevonden"
          supporting-text="De persoon bestaat niet, of je mag de gegevens niet inzien."
        />
      ) : (
        <QueryState query={query}>
          {person ? <PersonContent person={person} day={day} mayManage={mayManage} /> : null}
        </QueryState>
      )}
    </nldd-simple-section>
  );
}

type Editing =
  | null
  | 'identity'
  | 'hire'
  | 'scale'
  | 'target'
  | 'grant'
  | { revoke: FunctionGrant }
  | { removeHire: Hire };

interface ContentProps {
  person: Person;
  day: string;
  mayManage: boolean;
}

function useSave(onDone?: () => void) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ['team'] });
      onDone?.();
    },
    onError: (err) => setError(errorMessage(err)),
  });
  return { run: mutation.mutate, pending: mutation.isPending, error, setError };
}

function PersonContent({ person, day, mayManage }: ContentProps) {
  const [editing, setEditing] = useState<Editing>(null);
  const close = () => setEditing(null);
  const year = Number(day.slice(0, 4));
  const kpi = useQuery({
    queryKey: personKpiKey(person.id, year),
    queryFn: () => fetchPersonKpi(person.id, year),
    retry: false,
  });
  const revoked = typeof editing === 'object' && editing && 'revoke' in editing ? editing : null;
  const removedHire =
    typeof editing === 'object' && editing && 'removeHire' in editing ? editing : null;
  const direct = useSave(close);

  return (
    <>
      <nldd-container gap="32">
        <Identity
          person={person}
          day={day}
          mayManage={mayManage}
          onEdit={() => setEditing('identity')}
          onHire={() => setEditing('hire')}
          onRemoveHire={(hire) => setEditing({ removeHire: hire })}
        />
        {'current_assignment_count' in person ? <Staffing person={person} day={day} /> : null}
        {'scales' in person ? (
          <Scales person={person} mayManage={mayManage} onAdd={() => setEditing('scale')} />
        ) : null}
        {kpi.data ? (
          <KpiSection kpi={kpi.data} mayManage={mayManage} onEdit={() => setEditing('target')} />
        ) : null}
        {'function_grants' in person && (mayManage || (person.function_grants ?? []).length > 0) ? (
          <Rights
            person={person}
            mayManage={mayManage}
            onGrant={() => setEditing('grant')}
            onRevoke={(grant) => setEditing({ revoke: grant })}
          />
        ) : null}
        {mayManage ? <Login person={person} /> : null}
      </nldd-container>

      {mayManage ? (
        <>
          <Sheet
            open={editing === 'identity'}
            title={`Gegevens van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <IdentityForm person={person} day={day} onDone={close} />
          </Sheet>
          <Sheet
            open={editing === 'hire'}
            title={`Inhuur van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <HireForm person={person} day={day} onDone={close} />
          </Sheet>
          <Sheet
            open={editing === 'scale'}
            title={`Nieuwe inzetschaal van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <ScaleForm person={person} day={day} onDone={close} />
          </Sheet>
          <Sheet
            open={editing === 'target'}
            title={`Target ${year} van ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <TargetForm person={person} year={year} kpi={kpi.data ?? null} onDone={close} />
          </Sheet>
          <Sheet
            open={editing === 'grant'}
            title={`Recht toekennen aan ${person.name}`}
            dismissText="Annuleer"
            onClose={close}
          >
            <GrantForm person={person} onDone={close} />
          </Sheet>
          <ConfirmDialog
            open={revoked !== null}
            destructive
            text={
              revoked
                ? `Het recht ${functionLabel(revoked.revoke.function)} van ${person.name} intrekken?`
                : ''
            }
            supportingText={
              direct.error ??
              `${person.name} kan daarna niet meer wat dit recht toestaat. De intrekking komt met jouw naam in de auditlog.`
            }
            confirmText="Trek in"
            onClose={close}
            onConfirm={() => {
              if (revoked) direct.run(() => setFunction(person.id, revoked.revoke.function, false));
            }}
          />
          <ConfirmDialog
            open={removedHire !== null}
            destructive
            text={`De inhuur via ${removedHire?.removeHire.supplier ?? ''} verwijderen?`}
            supportingText={
              direct.error ??
              'De periode en de kostprijs verdwijnen. Was dit een vergissing in de invoer, leg de inhuur daarna opnieuw vast.'
            }
            confirmText="Verwijder inhuur"
            onClose={close}
            onConfirm={() => {
              const id = removedHire?.removeHire.id;
              if (id) direct.run(() => removeHire(person.id, id));
            }}
          />
        </>
      ) : null}
    </>
  );
}

// -- who this is and how they are engaged ---------------------------------------

function engagementText(person: Person, hire: Hire | null): string {
  const label = ENGAGEMENT_LABELS[engagementOf(person)];
  if (person.stage === 'prospective') {
    return person.starts_on ? `${label}, start op ${formatDate(person.starts_on)}` : label;
  }
  if (hire?.supplier) return `${label} via ${hire.supplier}`;
  return label;
}

interface IdentityProps extends ContentProps {
  onEdit: () => void;
  onHire: () => void;
  onRemoveHire: (hire: Hire) => void;
}

function Identity({ person, day, mayManage, onEdit, onHire, onRemoveHire }: IdentityProps) {
  const hire = currentHire(person, day);
  const prospective = person.stage === 'prospective';
  const otherHires = (person.hires ?? []).filter((h) => h !== hire && h.supplier);
  return (
    <Section
      title="Wie en hoe"
      action={mayManage ? { text: 'Wijzig gegevens', onClick: onEdit } : null}
    >
      <Facts label={`Gegevens van ${person.name}`}>
        <Fact
          label="Verbonden als"
          value={engagementText(person, hire)}
          {...(prospective
            ? {
                supportingText:
                  'Is al in te plannen. Inloggen kan pas als het e-mailadres bekend is.',
              }
            : !person.is_active
              ? { supportingText: 'Inactief: kan niet inloggen en wordt niet ingezet' }
              : {})}
        />
        <Fact
          label="E-mailadres"
          value={person.email ?? 'Nog geen e-mailadres'}
          {...(person.email ? {} : { supportingText: 'Het adres komt uit Wies zodra het bestaat' })}
        />
        <Fact label="Leidinggevende" value={person.manager_name ?? 'Geen leidinggevende'} />
        {hire?.valid_from ? (
          <Fact
            label="Inhuurperiode"
            value={formatPeriod(hire.valid_from, hire.valid_to ?? null)}
            {...(hire.contract_reference
              ? { supportingText: `Contractkenmerk ${hire.contract_reference}` }
              : {})}
          />
        ) : null}
        {typeof person.cost_monthly_rate_cents === 'number' ? (
          <Fact
            label="Kostprijs inhuur"
            value={`${formatEuro(person.cost_monthly_rate_cents)} per FTE per maand`}
            {...(typeof person.margin_monthly_cents === 'number'
              ? {
                  supportingText: `Marge ${formatEuro(person.margin_monthly_cents)} per FTE per maand: maandtarief min kostprijs`,
                }
              : {})}
          />
        ) : null}
        {otherHires.map((other) => (
          <Fact
            key={other.id ?? other.valid_from}
            label="Andere inhuurperiode"
            value={`${other.supplier}, ${formatPeriod(other.valid_from, other.valid_to ?? null)}`}
          />
        ))}
      </Facts>
      {/*
        For a prospective colleague this is where the reference of the hire
        in the recruitment system and the proposal to Wies will be linked
        from; the screens for those belong to the vacancies and Wies features.
      */}
      {mayManage && !prospective ? (
        <nldd-button-group>
          <Button
            appearance="neutral-transparent"
            text={hire ? 'Leg een nieuwe inhuurperiode vast' : 'Leg inhuur vast'}
            onClick={onHire}
          />
          {hire?.id ? (
            <Button
              appearance="neutral-transparent"
              text="Verwijder deze inhuur"
              onClick={() => onRemoveHire(hire)}
            />
          ) : null}
        </nldd-button-group>
      ) : null}
    </Section>
  );
}

function IdentityForm({
  person,
  day,
  onDone,
}: {
  person: Person;
  day: string;
  onDone: () => void;
}) {
  const save = useSave(onDone);
  const people = useQuery({
    queryKey: peopleKey(day, false),
    queryFn: () => fetchPeople(day, false),
  });
  const [name, setName] = useState(person.name);
  const [email, setEmail] = useState(person.email ?? '');
  const [managerId, setManagerId] = useState(person.manager_id ?? '');
  const [active, setActive] = useState(person.is_active);
  const soleBeheerder = person.is_sole_beheerder === true;
  return (
    <Form
      submitText="Bewaar gegevens"
      submitting={save.pending}
      error={save.error}
      onSubmit={() => {
        const address = email.trim();
        if (!name.trim() || (address !== '' && !address.includes('@'))) {
          save.setError('Vul een naam en een geldig e-mailadres in.');
          return;
        }
        save.run(() =>
          updatePerson(person.id, {
            name,
            // An empty address is left out: a prospective colleague has none yet.
            ...(address ? { email: address } : {}),
            manager_id: managerId || null,
            is_active: active,
          }),
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
      <SwitchField
        label={
          soleBeheerder
            ? 'Actief. Dit is de enige beheerder en kan daarom niet inactief worden'
            : 'Actief: kan inloggen en worden ingezet'
        }
        checked={active}
        onChange={setActive}
        disabled={soleBeheerder}
      />
    </Form>
  );
}

function HireForm({ person, day, onDone }: { person: Person; day: string; onDone: () => void }) {
  const save = useSave(onDone);
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
      onSubmit={() => {
        const cents = eurosToCents(cost);
        if (!supplier.trim() || !from || cents === null || cents < 0) {
          save.setError('Vul een leverancier, een ingangsdatum en een kostprijs in euro in.');
          return;
        }
        save.run(() =>
          addHire(person.id, {
            supplier,
            cost_monthly_rate_cents: cents,
            valid_from: from,
            valid_to: to || null,
            contract_reference: reference || null,
          }),
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

// -- what they work on --------------------------------------------------------------

function Staffing({ person, day }: { person: Person; day: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);
  const count = person.current_assignment_count ?? 0;
  const text =
    count === 0
      ? `Op ${formatDate(day)} niet ingezet`
      : `Op ${formatDate(day)} ingezet op ${count === 1 ? '1 opdracht' : `${count} opdrachten`}, samen ${formatPercent(person.current_fte_pct)}`;
  return (
    <Section title="Inzet">
      <Facts label={`Inzet van ${person.name}`}>
        <Fact label="Huidige inzet" value={text} />
      </Facts>
      <div ref={ref}>
        <nldd-link
          size="sm"
          href={`${PATHS.allocations}?persoon=${person.id}`}
          text="Bekijk de inzet op het Inzet-bord"
        />
      </div>
    </Section>
  );
}

// -- billing scale (class D) ----------------------------------------------------------

function Scales({
  person,
  mayManage,
  onAdd,
}: {
  person: Person;
  mayManage: boolean;
  onAdd: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);
  const scales = person.scales ?? [];
  const current =
    person.billing_scale === null || person.billing_scale === undefined
      ? 'Geen inzetschaal op de peildatum'
      : `Schaal ${person.billing_scale}${person.rate_category ? `, categorie ${person.rate_category}` : ''}`;
  return (
    <Section
      title="Inzetschaal"
      supportingText="De schaal waartegen deze persoon wordt gedeclareerd"
      action={mayManage ? { text: 'Nieuwe inzetschaal', onClick: onAdd } : null}
    >
      <Facts label={`Inzetschaal van ${person.name}`}>
        <Fact
          label="Nu"
          value={current}
          {...(typeof person.monthly_rate_cents === 'number'
            ? { supportingText: `Maandtarief ${formatEuro(person.monthly_rate_cents)} per FTE` }
            : {})}
        />
        {scales.map((entry) => (
          <Fact
            key={entry.id}
            label={formatPeriod(entry.valid_from, entry.valid_to)}
            value={`Schaal ${entry.billing_scale}`}
          />
        ))}
      </Facts>
      <div ref={ref}>
        <nldd-link size="sm" href={PATHS.rates} text="Bekijk de tarieven per categorie" />
      </div>
    </Section>
  );
}

function ScaleForm({ person, day, onDone }: { person: Person; day: string; onDone: () => void }) {
  const save = useSave(onDone);
  const [from, setFrom] = useState(day);
  const [scale, setScale] = useState('');
  return (
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
        save.run(() => addScale(person.id, { valid_from: from, billing_scale: number }));
      }}
    >
      <DateField
        label="Vanaf"
        supportingLabel="De vorige periode eindigt de dag ervoor"
        value={from}
        onChange={setFrom}
        required
      />
      <TextField label="Schaal" value={scale} onChange={setScale} keyboard="numeric" required />
    </Form>
  );
}

// -- KPI (class F) ------------------------------------------------------------------------

function KpiSection({
  kpi,
  mayManage,
  onEdit,
}: {
  kpi: Kpi;
  mayManage: boolean;
  onEdit: () => void;
}) {
  return (
    <Section
      title={`Declarabiliteit ${kpi.year}`}
      action={mayManage ? { text: 'Stel target in', onClick: onEdit } : null}
    >
      {kpi.unavailable_reason ? (
        <nldd-inline-dialog text={kpi.unavailable_reason} />
      ) : (
        <Facts label={`Declarabiliteit ${kpi.year}`}>
          <Fact
            label="Target"
            value={
              kpi.target_pct === null
                ? 'Geen target ingesteld'
                : `${formatPercent(kpi.target_pct)}, ${formatEuro(kpi.target_cents)}`
            }
          />
          <Fact
            label="Gerealiseerd"
            value={formatEuro(kpi.realised_cents)}
            supportingText="Afgesloten maanden, met de vastgestelde inzet"
          />
          <Fact
            label="Nog gepland"
            value={formatEuro(kpi.forecast_cents)}
            supportingText="Open maanden, met de geplande inzet"
          />
          <Fact label="Verwacht totaal" value={formatEuro(kpi.realisation_cents)} />
        </Facts>
      )}
    </Section>
  );
}

function TargetForm({
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
  const save = useSave(onDone);
  const [value, setValue] = useState(
    kpi?.target_pct ? String(Number(kpi.target_pct)).replace('.', ',') : '',
  );
  return (
    <Form
      submitText="Bewaar target"
      submitting={save.pending}
      error={save.error}
      onSubmit={() => {
        const pct = percentInput(value);
        if (pct === null || Number(pct) > 100) {
          save.setError('Vul een percentage van 0 tot en met 100 in.');
          return;
        }
        save.run(() => setKpiTarget(person.id, year, pct));
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

// -- rights in grip ------------------------------------------------------------------------

function grantLine(grant: FunctionGrant): string {
  const by = grant.granted_by_name
    ? `door ${grant.granted_by_name}`
    : 'bij de inrichting van de instantie';
  return `Sinds ${formatDate(grant.since)}, toegekend ${by}`;
}

interface RightsProps {
  person: Person;
  mayManage: boolean;
  onGrant: () => void;
  onRevoke: (grant: FunctionGrant) => void;
}

/**
 * What the person may do in grip. Each right is granted and revoked as an
 * explicit action; nothing changes at the touch of a control.
 */
function Rights({ person, mayManage, onGrant, onRevoke }: RightsProps) {
  const grants = person.function_grants ?? [];
  const available = FUNCTIONS.filter((fn) => !grants.some((g) => g.function === fn.id));
  return (
    <Section
      title="Rechten in grip"
      supportingText="Wat deze persoon in grip mag, bovenop wat volgt uit eigen opdrachten en medewerkers"
      action={
        mayManage && available.length > 0 ? { text: 'Ken een recht toe', onClick: onGrant } : null
      }
    >
      {grants.length === 0 ? (
        <nldd-inline-dialog
          text="Geen rechten toegekend"
          supporting-text="Deze persoon ziet de eigen gegevens, de eigen opdrachten en de eigen medewerkers."
        />
      ) : (
        <nldd-table
          accessible-label={`Rechten in grip van ${person.name}`}
          columns={
            mayManage
              ? 'minmax(160px,1fr) minmax(200px,2fr) 110px'
              : 'minmax(160px,1fr) minmax(200px,2fr)'
          }
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Recht" />
            <nldd-text-cell text="Toegekend" />
            {mayManage ? <nldd-text-cell text="Actie" /> : null}
          </nldd-table-row>
          {grants.map((grant) => {
            const sole = grant.function === 'beheerder' && person.is_sole_beheerder === true;
            return (
              <nldd-table-row key={grant.function}>
                <nldd-text-cell
                  text={functionLabel(grant.function)}
                  supporting-text={
                    FUNCTIONS.find((fn) => fn.id === grant.function)?.description ?? ''
                  }
                />
                <nldd-text-cell
                  text={grantLine(grant)}
                  {...(sole
                    ? {
                        'supporting-text':
                          'Dit is de enige beheerder. Ken eerst iemand anders dit recht toe; zonder beheerder kan niemand de instantie beheren.',
                      }
                    : {})}
                />
                {mayManage ? (
                  <nldd-cell>
                    {sole ? null : (
                      <Button
                        size="sm"
                        text="Trek in"
                        accessibleLabel={`Trek het recht ${functionLabel(grant.function)} van ${person.name} in`}
                        onClick={() => onRevoke(grant)}
                      />
                    )}
                  </nldd-cell>
                ) : null}
              </nldd-table-row>
            );
          })}
        </nldd-table>
      )}
    </Section>
  );
}

function GrantForm({ person, onDone }: { person: Person; onDone: () => void }) {
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

// -- login -----------------------------------------------------------------------------------

/**
 * The login of a person, for the beheerder. A person is bound to an account
 * of the identity provider on the first login. When that account changes
 * (the provider was set up again, or the person got a new account there) the
 * login is refused until the binding is removed here.
 */
function Login({ person }: { person: Person }) {
  const save = useSave();
  const [confirming, setConfirming] = useState(false);
  const state = useQuery({
    queryKey: loginKey(person.id),
    queryFn: () => fetchLoginState(person.id),
    retry: false,
  });
  if (!state.data) return null;
  const bound = state.data.bound;
  return (
    <Section
      title="Inloggen"
      supportingText={
        bound
          ? 'Gekoppeld aan een account bij de identiteitsprovider'
          : 'Nog niet ingelogd; de eerste keer inloggen koppelt het account'
      }
      action={
        bound
          ? {
              text: 'Ontkoppel login',
              accessibleLabel: `Ontkoppel de login van ${person.name}`,
              onClick: () => setConfirming(true),
            }
          : null
      }
    >
      {save.error ? <nldd-banner variant="critical" text={save.error} /> : null}
      <ConfirmDialog
        open={confirming}
        text={`De login van ${person.name} ontkoppelen?`}
        supportingText="Doe dit als de persoon niet meer kan inloggen omdat het account bij de identiteitsprovider is vervangen. De volgende keer inloggen met hetzelfde e-mailadres koppelt het nieuwe account."
        confirmText="Ontkoppel login"
        onClose={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          save.run(() => unbindLogin(person.id));
        }}
      />
    </Section>
  );
}
