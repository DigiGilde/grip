import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { boardKeys, fetchBoard } from '@/features/allocations/board/api';
import { formatEuro, formatPercent, formatDate } from '@/lib/format';
import { RouterLinks } from '@/layout/RouterLinks';
import { PATHS } from '@/paths';
import { ActionBar, type ActionBarFilter } from '@/ui/ActionBar';
import { OpenCell, OpenRow } from '@/ui/RowActions';
import { createPerson, fetchPeople, peopleKey, today, type Person } from './api';
import { DateField, SelectField, TextField } from './ui/controls';
import { Form, Sheet } from './ui/overlays';
import { orderPeople } from './peopleOrder';
import { anyHas } from './ui/rows';
import { EmptyRows, QueryState } from './ui/states';

const SHOW_OPTIONS = [
  { value: 'active', label: 'Actieve personen' },
  { value: 'all', label: 'Ook inactieve personen' },
];

/**
 * Under a name in the list only what sets this person apart: not yet
 * started, or no longer active. The address is on the person's own page.
 */
function listLine(person: Person): string {
  const parts = [
    person.stage === 'prospective' && person.starts_on
      ? `start op ${formatDate(person.starts_on)}`
      : null,
    person.is_active ? null : 'inactief',
  ].filter(Boolean);
  return parts.join(', ');
}

/**
 * The persons the asker may see, as a list to scan: how much each works now,
 * and what about their work needs attention, most urgent first. A column is
 * only drawn when at least one row carries its field. The row opens the
 * person.
 */
export function PeopleView({ viewFilter }: { viewFilter?: ActionBarFilter }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const day = today();
  const [includeInactive, setIncludeInactive] = useState(false);
  const query = useQuery({
    queryKey: peopleKey(day, includeInactive),
    queryFn: () => fetchPeople(day, includeInactive),
  });
  const people = query.data?.items ?? [];
  const mayManage = query.data?.may_manage ?? false;
  const showStaffing = anyHas(people, 'current_fte_pct');
  // The board says where someone's work ends; it decides per row what this
  // reader may see, so a person without a row simply has no signal.
  const board = useQuery({
    queryKey: boardKeys.board(''),
    queryFn: () => fetchBoard(''),
    enabled: showStaffing,
    retry: false,
  });
  const rows = new Map((board.data?.persons ?? []).map((row) => [row.person_id, row] as const));
  const ordered = orderPeople(people, rows);

  const [adding, setAdding] = useState(false);
  const openPerson = (id: string) => navigate(PATHS.teamPerson.replace(':personId', id));

  const showRate = anyHas(people, 'billing_scale');
  // A list in which nobody has a manager named has no column for it.
  const showManager = people.some((person) => person.manager_name);
  const columns = [
    'minmax(220px,2fr)',
    ...(showStaffing ? ['200px', 'minmax(200px,1.5fr)'] : []),
    ...(showManager ? ['minmax(160px,1fr)'] : []),
    ...(showRate ? ['90px', '130px'] : []),
  ].join(' ');
  const narrow = showStaffing ? 'minmax(160px,1fr) 120px' : 'minmax(160px,1fr)';

  return (
    <>
      <RouterLinks>
        <ActionBar
          label="Personen filteren en acties"
          filters={[
            ...(viewFilter ? [viewFilter] : []),
            ...(mayManage
              ? [
                  {
                    label: 'Toon',
                    value: includeInactive ? 'all' : 'active',
                    onChange: (value: string) => setIncludeInactive(value === 'all'),
                    options: SHOW_OPTIONS,
                    width: '240px',
                  },
                ]
              : []),
          ]}
          actions={
            mayManage
              ? [
                  { text: 'Voorstellen uit Wies', href: PATHS.wiesProposals },
                  { text: 'Nieuwe persoon', onClick: () => setAdding(true), primary: true },
                ]
              : []
          }
        />
      </RouterLinks>

      <QueryState query={query}>
        <nldd-table accessible-label="Personen" columns={columns} sm-columns={narrow}>
          <nldd-table-row slot="header">
            <nldd-text-cell text="Naam" />
            {showStaffing ? (
              <>
                <nldd-text-cell text="Inzet nu" />
                <nldd-text-cell text="Vooruit" hide-below="md" />
              </>
            ) : null}
            {showManager ? <nldd-text-cell text="Leidinggevende" hide-below="md" /> : null}
            {showRate ? (
              <>
                <nldd-text-cell text="Schaal" hide-below="md" />
                <nldd-text-cell text="Maandtarief" horizontal-alignment="right" hide-below="md" />
              </>
            ) : null}
          </nldd-table-row>
          {ordered.map(({ person, signal }) => (
            <OpenRow key={person.id} onOpen={() => openPerson(person.id)}>
              <OpenCell
                text={person.name}
                {...(listLine(person) ? { supportingText: listLine(person) } : {})}
                accessibleLabel={`Bekijk ${person.name}`}
                onOpen={() => openPerson(person.id)}
              />
              {showStaffing ? (
                <>
                  <nldd-cell>
                    {'current_fte_pct' in person ? (
                      <nldd-progress-bar
                        size="sm"
                        max={100}
                        value={Math.min(100, Number(person.current_fte_pct ?? 0))}
                        color={Number(person.current_fte_pct ?? 0) > 100 ? 'warning' : 'accent'}
                        text={formatPercent(person.current_fte_pct ?? '0')}
                        value-display="none"
                        accessible-label={`${person.name}: nu ${formatPercent(person.current_fte_pct ?? '0')} ingezet`}
                      />
                    ) : null}
                  </nldd-cell>
                  <nldd-cell hide-below="md">
                    {signal.text ? (
                      // Colour only for what is wrong now: planned above what
                      // a person can do. Work that ends is a fact, said quietly.
                      <nldd-text size="sm" color={signal.attention ? 'warning' : 'secondary'}>
                        {signal.text}
                      </nldd-text>
                    ) : null}
                  </nldd-cell>
                </>
              ) : null}
              {showManager ? (
                <nldd-text-cell text={person.manager_name ?? ''} hide-below="md" />
              ) : null}
              {showRate ? (
                <>
                  <nldd-text-cell
                    hide-below="md"
                    text={
                      typeof person.billing_scale === 'number' ? String(person.billing_scale) : ''
                    }
                  />
                  <nldd-text-cell
                    hide-below="md"
                    horizontal-alignment="right"
                    text={
                      typeof person.monthly_rate_cents === 'number'
                        ? formatEuro(person.monthly_rate_cents)
                        : ''
                    }
                  />
                </>
              ) : null}
            </OpenRow>
          ))}
          <EmptyRows text="Er zijn geen personen om te tonen" />
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
    <Sheet open={open} title="Nieuwe persoon" dismissText="Annuleer" onClose={onClose}>
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
