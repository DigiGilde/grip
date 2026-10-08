import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { Button } from '@/features/team/ui/controls';
import { EmptyRows, QueryState } from '@/features/team/ui/states';
import {
  fetchSyncStatus,
  organisationKeys,
  searchOrganisations,
  startSync,
  type Organisation,
  type SyncStatus,
} from './api';
import { AddOrganisationForm, OrganisationPicker } from './OrganisationPicker';
import { organisationPlace, organisationText, syncSummary } from './text';
import './nldd';

const POLL_MS = 5000;

function LastRun({ status }: { status: SyncStatus }) {
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
  if (!run) {
    return (
      <nldd-inline-dialog
        text="Het register is nog niet opgehaald"
        supporting-text="Tot die tijd bestaat de lijst alleen uit organisaties die zelf zijn toegevoegd."
      />
    );
  }
  if (run.status === 'failed') {
    return (
      <nldd-banner
        variant="critical"
        text={`Ophalen op ${formatDate(run.finished_at)} is mislukt`}
        supporting-text={run.error ?? 'Er is niets gewijzigd.'}
      />
    );
  }
  return (
    <nldd-banner
      variant="success"
      text={`Laatst opgehaald op ${formatDate(run.finished_at)}`}
      supporting-text={syncSummary(run.result)}
    />
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

/**
 * For the beheerder: where the list of organisations comes from, when it was
 * last brought in line with the public register, and what was added by hand.
 */
export function OrganisationsAdminPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const [problem, setProblem] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
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

  // When a run ends, every list of organisations on screen is out of date.
  const running = status.data?.running ?? false;
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) {
      void queryClient.invalidateQueries({ queryKey: organisationKeys.all });
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
    <nldd-simple-section>
      <PageHeading text="Organisaties" instanceName={instance?.name} />
      <nldd-container gap="32">
        <nldd-container gap="16">
          <nldd-title size={4} text="Overheidsregister" heading-level={2} />
          <nldd-rich-text>
            <p>
              De lijst met organisaties komt uit het openbare register van
              organisaties.overheid.nl. Ophalen brengt de lijst in lijn met het register:
              nieuwe organisaties komen erbij, gewijzigde worden bijgewerkt en opgeheven
              organisaties krijgen een einddatum. Een organisatie waar een opdracht naar
              verwijst verdwijnt nooit.
            </p>
          </nldd-rich-text>
          <QueryState query={status}>
            {status.data ? (
              <>
                {problem ? <nldd-banner variant="critical" text={problem} /> : null}
                <LastRun status={status.data} />
                <nldd-text-cell
                  text={`${status.data.registry_organisations} organisaties uit het register`}
                  supporting-text={`${status.data.manual_organisations} zelf toegevoegd`}
                />
                <nldd-container layout="wrap" gap="16">
                  <Button
                    text="Haal het register op"
                    appearance="primary"
                    loading={sync.isPending}
                    disabled={running}
                    onClick={() => sync.mutate()}
                  />
                </nldd-container>
              </>
            ) : null}
          </QueryState>
        </nldd-container>

        <nldd-container gap="16">
          <nldd-title size={4} text="Zelf toegevoegd" heading-level={2} />
          <nldd-rich-text>
            <p>
              Partijen die niet in het register staan, zoals een stichting of een bedrijf, en
              eenheden binnen een organisatie, zoals een gilde of een team.
            </p>
          </nldd-rich-text>
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
                  <nldd-text-cell text={organisationPlace(organisation) || 'Staat op zichzelf'} />
                </nldd-table-row>
              ))}
              <EmptyRows
                text="Er is nog niets zelf toegevoegd"
                supportingText="Toevoegen kan hier, en overal waar je een organisatie kiest."
              />
            </nldd-table>
          </QueryState>
          {adding ? (
            <AddOrganisationForm
              initialName=""
              onAdded={() => setAdding(false)}
              onCancel={() => setAdding(false)}
            />
          ) : (
            <nldd-container layout="wrap" gap="16">
              <Button text="Organisatie toevoegen" onClick={() => setAdding(true)} />
            </nldd-container>
          )}
        </nldd-container>

        <nldd-container gap="16">
          <nldd-title size={4} text="Opzoeken" heading-level={2} />
          <OrganisationPicker
            label="Organisatie"
            supportingLabel="Zoek op naam of afkorting om te zien wat de lijst over een organisatie weet"
            value={lookedUp?.id ?? null}
            onChange={setLookedUp}
            allowAdd={false}
          />
          {lookedUp ? <Details organisation={lookedUp} /> : null}
        </nldd-container>
      </nldd-container>
    </nldd-simple-section>
  );
}
