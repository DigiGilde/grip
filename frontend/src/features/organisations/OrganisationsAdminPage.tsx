import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import { TextField } from '@/ui/fields';
import { ErrorNotice, FormSheet, Page, Quiet, Section, Stack } from '@/ui/layout';
import { EmptyRows, QueryState } from '@/features/team/ui/states';
import {
  createOrganisation,
  fetchSyncStatus,
  organisationKeys,
  searchOrganisations,
  startSync,
  type Organisation,
  type SyncStatus,
} from './api';
import { OrganisationPicker } from './OrganisationPicker';
import { organisationPlace, organisationText, syncSummary } from './text';
import './nldd';
import { useAdminBack } from '@/layout/useAdminBack';

const POLL_MS = 5000;

/** The state of the register in one calm line; a notice only for what needs attention. */
function RegisterState({ status, justFetched }: { status: SyncStatus; justFetched: boolean }) {
  const run = status.last_run;
  if (status.running) {
    return (
      <nldd-inline-dialog
        variant="loading"
        text="Het register wordt opgehaald"
        supporting-text="Dat duurt een paar minuten. Je kunt deze pagina verlaten; het ophalen gaat door."
      />
    );
  }
  const counts = `${status.registry_organisations} organisaties uit het register, ${status.manual_organisations} zelf toegevoegd.`;
  if (!run) return <Quiet>Het register is nog niet opgehaald. {counts}</Quiet>;
  if (run.status === 'failed') {
    return (
      <Stack gap="related">
        <nldd-banner
          variant="critical"
          text={`Ophalen op ${formatDate(run.finished_at)} is mislukt`}
          supporting-text={run.error ?? 'Er is niets gewijzigd.'}
        />
        <Quiet>{counts}</Quiet>
      </Stack>
    );
  }
  return (
    <Stack gap="related">
      {justFetched ? (
        <nldd-banner
          variant="success"
          size="sm"
          text="Het register is opgehaald"
          supporting-text={syncSummary(run.result)}
        />
      ) : null}
      <Quiet>
        Laatst opgehaald op {formatDate(run.finished_at)}. {counts}
      </Quiet>
    </Stack>
  );
}

function Details({ organisation }: { organisation: Organisation }) {
  const rows: [string, string][] = [
    ['Naam', organisationText(organisation)],
    ['Valt onder', organisationPlace(organisation) || 'Niets: dit is het hoogste niveau'],
    ['Soort', organisation.organisation_types.join(', ') || 'Niet opgegeven'],
    ['Herkomst', organisation.source === 'registry' ? 'Overheidsregister' : 'Zelf toegevoegd'],
    ['TOOI-URI', organisation.tooi_uri ?? 'Geen'],
  ];
  if (organisation.instance_uri) rows.push(['Grip-instantie', organisation.instance_uri]);
  return (
    <nldd-list accessible-label={`Gegevens van ${organisation.label}`} appearance="box-base">
      {rows.map(([label, value]) => (
        <nldd-list-item key={label}>
          <nldd-text-cell text={label} supporting-text={value} />
        </nldd-list-item>
      ))}
    </nldd-list>
  );
}

/** Adding an organisation by hand: a name and, for a unit, what it belongs to. */
function AddSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [parent, setParent] = useState<Organisation | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () => createOrganisation({ name: name.trim(), parent_id: parent?.id ?? null }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: organisationKeys.all });
      onClose();
    },
    onError: (error) => setProblem(errorMessage(error)),
  });
  return (
    <FormSheet
      open={open}
      title="Organisatie toevoegen"
      submitText="Voeg toe"
      busy={add.isPending}
      error={problem}
      onClose={onClose}
      onSubmit={() => {
        if (!name.trim()) {
          setProblem('Geef de organisatie een naam.');
          return;
        }
        setProblem(null);
        add.mutate();
      }}
    >
      <TextField
        label="Naam"
        hint="Voor een partij die niet in het overheidsregister staat, of een eenheid binnen een organisatie"
        value={name}
        onChange={setName}
        required
      />
      <OrganisationPicker
        label="Hoort bij"
        supportingLabel="Kies de organisatie waar deze eenheid onder valt"
        value={parent?.id ?? null}
        onChange={setParent}
        optional
        allowAdd={false}
      />
    </FormSheet>
  );
}

/**
 * For the beheerder: where the list of organisations comes from, when it was
 * last brought in line with the public register, and what was added by hand.
 */
export function OrganisationsAdminPage() {
  const instance = useInstance();
  const adminBack = useAdminBack();
  const queryClient = useQueryClient();
  const [problem, setProblem] = useState<string | null>(null);
  // The key makes every opening start with an empty form.
  const [adding, setAdding] = useState({ open: false, session: 0 });
  const [lookedUp, setLookedUp] = useState<Organisation | null>(null);

  const status = useQuery({
    queryKey: organisationKeys.sync,
    queryFn: fetchSyncStatus,
    refetchInterval: (query) => (query.state.data?.running ? POLL_MS : false),
  });
  const manual = useQuery({
    queryKey: organisationKeys.search({ source: 'manual', page_size: 100 }),
    queryFn: () => searchOrganisations({ source: 'manual', page_size: 100 }),
  });

  // When a run ends, every list of organisations on screen is out of date,
  // and that is the one moment its result is news.
  const running = status.data?.running ?? false;
  const wasRunning = useRef(false);
  const [justFetched, setJustFetched] = useState(false);
  useEffect(() => {
    if (wasRunning.current && !running) {
      void queryClient.invalidateQueries({ queryKey: organisationKeys.all });
      setJustFetched(true);
    }
    wasRunning.current = running;
  }, [running, queryClient]);

  const sync = useMutation({
    mutationFn: startSync,
    onSuccess: (next) => {
      setProblem(null);
      queryClient.setQueryData(organisationKeys.sync, next);
    },
    onError: (error) => setProblem(errorMessage(error)),
  });

  const manualItems = manual.data?.items ?? [];

  return (
    <Page title="Organisaties" instanceName={instance?.name} spacing="sections" back={adminBack}>
      <ActionBar
        label="Organisaties bijwerken"
        actions={[
          {
            text: 'Organisatie toevoegen',
            onClick: () => setAdding((current) => ({ open: true, session: current.session + 1 })),
          },
          ...(status.data
            ? [
                {
                  text: 'Haal het register op',
                  primary: true,
                  loading: sync.isPending,
                  disabled: running,
                  onClick: () => sync.mutate(),
                },
              ]
            : []),
        ]}
      />

      <Section title="Overheidsregister" description="Uit organisaties.overheid.nl">
        <QueryState query={status}>
          {status.data ? (
            <>
              {problem ? <ErrorNotice message={problem} /> : null}
              <RegisterState status={status.data} justFetched={justFetched} />
            </>
          ) : null}
        </QueryState>
      </Section>

      <Section
        title="Zelf toegevoegd"
        description="Partijen buiten het register, en eenheden binnen een organisatie"
      >
        <QueryState query={manual}>
          <nldd-table
            accessible-label="Organisaties die zelf zijn toegevoegd"
            columns="minmax(200px,2fr) minmax(240px,3fr)"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Naam" />
              <nldd-text-cell text="Valt onder" />
            </nldd-table-row>
            {manualItems.map((organisation) => (
              <nldd-table-row key={organisation.id}>
                <nldd-text-cell text={organisationText(organisation)} />
                <nldd-text-cell text={organisationPlace(organisation)} />
              </nldd-table-row>
            ))}
            <EmptyRows text="Nog niets zelf toegevoegd" />
          </nldd-table>
        </QueryState>
      </Section>

      <Section title="Opzoeken">
        <OrganisationPicker
          label="Organisatie"
          supportingLabel="Op naam of afkorting"
          value={lookedUp?.id ?? null}
          onChange={setLookedUp}
          allowAdd={false}
        />
        {lookedUp ? <Details organisation={lookedUp} /> : null}
      </Section>
      <AddSheet
        key={adding.session}
        open={adding.open}
        onClose={() => setAdding((current) => ({ ...current, open: false }))}
      />
    </Page>
  );
}
