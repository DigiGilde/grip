import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { formatEuro } from '@/lib/format';
import { PATHS } from '@/paths';
import {
  createPerson,
  fetchPeople,
  functionLabel,
  peopleKey,
  personSubtitle,
  today,
  type Person,
} from './api';
import { Button, DateField, SelectField, SwitchField, TextField } from './ui/controls';
import { Form, Sheet } from './ui/overlays';
import { anyHas } from './ui/rows';
import { EmptyRows, QueryState } from './ui/states';

function amount(person: Person, field: keyof Person): string {
  if (!(field in person)) return '';
  const value = person[field];
  return typeof value === 'number' ? formatEuro(value) : 'Onbekend';
}

/**
 * The persons the asker may see. A column is only drawn when at least one
 * row carries its field; a cell stays empty for a person whose value the
 * asker may not see.
 */
export function PeopleView() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [day, setDay] = useState(today());
  const [includeInactive, setIncludeInactive] = useState(false);
  const query = useQuery({
    queryKey: peopleKey(day, includeInactive),
    queryFn: () => fetchPeople(day, includeInactive),
    enabled: /^\d{4}-\d{2}-\d{2}$/.test(day),
  });
  const people = query.data?.items ?? [];
  const mayManage = query.data?.may_manage ?? false;

  const [adding, setAdding] = useState(false);
  // A person has a page of their own; the reference day goes along.
  const openPerson = (id: string) =>
    navigate(`${PATHS.teamPerson.replace(':personId', id)}?peildatum=${day}`);

  const showFunctions = anyHas(people, 'functions');
  const showRate = anyHas(people, 'billing_scale');
  const showCost = anyHas(people, 'cost_monthly_rate_cents');

  const columns = [
    'minmax(180px,2fr)',
    'minmax(140px,1fr)',
    ...(showFunctions ? ['minmax(140px,1fr)'] : []),
    ...(showRate ? ['90px', '100px', 'minmax(120px,1fr)'] : []),
    ...(showCost ? ['minmax(120px,1fr)', 'minmax(120px,1fr)'] : []),
    '110px',
  ].join(' ');

  return (
    <>
      <nldd-container layout="wrap" gap="16" vertical-alignment="bottom">
        <DateField
          width="280px"
          label="Peildatum"
          supportingLabel="Schaal, tarief en inhuur op deze dag"
          value={day}
          onChange={(value) => value && setDay(value)}
        />
        {mayManage ? (
          <>
            <SwitchField
              label="Toon ook inactieve personen"
              checked={includeInactive}
              onChange={setIncludeInactive}
            />
            <Button text="Persoon toevoegen" onClick={() => setAdding(true)} />
          </>
        ) : null}
        {showRate ? (
          <Button
            appearance="neutral-transparent"
            text="Bekijk de tarieven per categorie"
            onClick={() => navigate(PATHS.rates)}
          />
        ) : null}
      </nldd-container>

      <QueryState query={query}>
        <nldd-table accessible-label="Personen" columns={columns}>
          <nldd-table-row slot="header">
            <nldd-text-cell text="Naam" />
            <nldd-text-cell text="Leidinggevende" />
            {showFunctions ? <nldd-text-cell text="Rechten in grip" /> : null}
            {showRate ? (
              <>
                <nldd-text-cell text="Inzetschaal" />
                <nldd-text-cell text="Categorie" />
                <nldd-text-cell text="Maandtarief" horizontal-alignment="right" />
              </>
            ) : null}
            {showCost ? (
              <>
                <nldd-text-cell text="Kostprijs inhuur" horizontal-alignment="right" />
                <nldd-text-cell text="Marge per maand" horizontal-alignment="right" />
              </>
            ) : null}
            <nldd-text-cell text="Actie" />
          </nldd-table-row>
          {people.map((person) => (
            <nldd-table-row key={person.id}>
              <nldd-text-cell text={person.name} supporting-text={personSubtitle(person)} />
              <nldd-text-cell text={person.manager_name ?? ''} />
              {showFunctions ? (
                <nldd-text-cell text={(person.functions ?? []).map(functionLabel).join(', ')} />
              ) : null}
              {showRate ? (
                <>
                  <nldd-text-cell
                    text={'billing_scale' in person ? String(person.billing_scale ?? 'Geen') : ''}
                  />
                  <nldd-text-cell
                    text={'rate_category' in person ? (person.rate_category ?? 'Geen') : ''}
                  />
                  <nldd-text-cell
                    text={amount(person, 'monthly_rate_cents')}
                    horizontal-alignment="right"
                  />
                </>
              ) : null}
              {showCost ? (
                <>
                  <nldd-text-cell
                    text={
                      typeof person.cost_monthly_rate_cents === 'number'
                        ? formatEuro(person.cost_monthly_rate_cents)
                        : ''
                    }
                    horizontal-alignment="right"
                  />
                  <nldd-text-cell
                    text={
                      typeof person.margin_monthly_cents === 'number'
                        ? formatEuro(person.margin_monthly_cents)
                        : ''
                    }
                    horizontal-alignment="right"
                  />
                </>
              ) : null}
              <nldd-cell>
                <Button
                  size="sm"
                  text="Bekijk"
                  accessibleLabel={`Bekijk ${person.name}`}
                  onClick={() => openPerson(person.id)}
                />
              </nldd-cell>
            </nldd-table-row>
          ))}
          <EmptyRows
            text="Er zijn geen personen om te tonen"
            supportingText="Je ziet hier de personen van wie je gegevens mag inzien."
          />
        </nldd-table>
      </QueryState>

      <NewPersonSheet
        open={adding}
        people={people}
        onClose={() => setAdding(false)}
        onCreated={async (person) => {
          setAdding(false);
          await queryClient.invalidateQueries({ queryKey: ['team'] });
          openPerson(person.id);
        }}
      />
    </>
  );
}

interface NewPersonSheetProps {
  open: boolean;
  people: Person[];
  onClose: () => void;
  onCreated: (person: Person) => void;
}

function NewPersonSheet({ open, people, onClose, onCreated }: NewPersonSheetProps) {
  return (
    <Sheet open={open} title="Persoon toevoegen" dismissText="Annuleer" onClose={onClose}>
      <NewPersonForm people={people} onCreated={onCreated} />
    </Sheet>
  );
}

function NewPersonForm({ people, onCreated }: Pick<NewPersonSheetProps, 'people' | 'onCreated'>) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [startDate, setStartDate] = useState('');
  const [managerId, setManagerId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: createPerson,
    onSuccess: onCreated,
    onError: (err) => setError(errorMessage(err)),
  });
  return (
    <Form
      submitText="Voeg toe"
      submitting={create.isPending}
      error={error}
      onSubmit={() => {
        const address = email.trim();
        if (!name.trim()) {
          setError('Vul een naam in.');
          return;
        }
        if (address && !address.includes('@')) {
          setError('Dit is geen geldig e-mailadres.');
          return;
        }
        if (!address && !startDate) {
          setError('Vul een e-mailadres in, of een startdatum voor een aanstaande collega.');
          return;
        }
        create.mutate({
          name,
          manager_id: managerId || null,
          ...(address ? { email: address } : { start_date: startDate }),
        });
      }}
    >
      <TextField label="Naam" value={name} onChange={setName} autocomplete="off" required />
      <TextField
        label="E-mailadres"
        supportingLabel="Hiermee logt de persoon in met SSO Rijk. Leeg laten kan voor een aanstaande collega."
        value={email}
        onChange={setEmail}
        type="email"
        autocomplete="off"
      />
      <DateField
        label="Startdatum"
        supportingLabel="Nodig als er nog geen e-mailadres is. De persoon is dan meteen in te plannen."
        value={startDate}
        onChange={setStartDate}
      />
      <SelectField
        label="Leidinggevende"
        optional
        value={managerId}
        onChange={setManagerId}
        emptyLabel="Geen"
        options={people.map((p) => ({ value: p.id, label: p.name }))}
      />
    </Form>
  );
}
