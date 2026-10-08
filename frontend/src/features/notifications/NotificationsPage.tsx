import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { Button, TextInput } from '@/features/assignments/ui';
import { CheckboxInput } from '@/features/quotes/ui';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { ROW_ACTIONS_COLUMN, RowActions } from '@/ui/RowActions';
import {
  EmptyNotice,
  ErrorNotice,
  Facts,
  FormFields,
  FormSheet,
  Loading,
  Page,
  Quiet,
  Section,
  Stack,
} from '@/ui/layout';
import {
  removeDevice,
  savePreference,
  sendTest,
  thisDeviceId,
  type Device,
  type Preference,
  type PreferenceChange,
} from './api';
import { blockedText } from './state';
import { usePush } from './usePush';

function clock(value: string | null): string {
  return value ? value.slice(0, 5) : '';
}

function quietText(preference: Preference): string {
  const hours =
    preference.quiet_from && preference.quiet_until
      ? `Van ${clock(preference.quiet_from)} tot ${clock(preference.quiet_until)}`
      : 'Geen stille uren';
  return preference.weekends_quiet ? `${hours}, en in het weekend` : hours;
}

function usedText(device: Device): string {
  return device.last_success_at
    ? `Laatste melding op ${formatDate(device.last_success_at)}`
    : 'Nog geen melding gekregen';
}

const TIME = /^([01]?\d|2[0-3]):[0-5]\d$/;

/** How grip tells you that something waits for you, and on which devices. */
export function NotificationsPage() {
  const instance = useInstance();
  const { query, state, busy, error, on, off, refresh } = usePush();
  const [saveError, setSaveError] = useState<string | null>(null);
  const [quietOpen, setQuietOpen] = useState(false);
  const [from, setFrom] = useState('');
  const [until, setUntil] = useState('');
  const [weekends, setWeekends] = useState(true);
  const [quietError, setQuietError] = useState<string | null>(null);
  const [tested, setTested] = useState(false);

  const save = useMutation({
    mutationFn: (change: PreferenceChange) => savePreference(change),
    onSuccess: async () => {
      setQuietOpen(false);
      await refresh();
    },
    onError: (failure) => {
      setSaveError(errorMessage(failure));
      setQuietError(errorMessage(failure));
    },
  });
  const remove = useMutation({
    mutationFn: removeDevice,
    onSuccess: refresh,
    onError: (failure) => setSaveError(errorMessage(failure)),
  });
  const test = useMutation({
    mutationFn: sendTest,
    onSuccess: () => setTested(true),
    onError: (failure) => setSaveError(errorMessage(failure)),
  });

  const data = query.data;
  const preference = data?.preference;
  const here = thisDeviceId();
  const blocked = blockedText(state);
  const change = (values: PreferenceChange) => {
    setSaveError(null);
    save.mutate(values);
  };
  const editQuiet = () => {
    if (!preference) return;
    setFrom(clock(preference.quiet_from) || '19:00');
    setUntil(clock(preference.quiet_until) || '07:30');
    setWeekends(preference.weekends_quiet);
    setQuietError(null);
    setQuietOpen(true);
  };
  const submitQuiet = () => {
    if (!from.trim() && !until.trim()) {
      save.mutate({ quiet: false, weekends_quiet: weekends });
      return;
    }
    if (!TIME.test(from.trim()) || !TIME.test(until.trim())) {
      setQuietError('Vul twee tijden in als 19:00 en 07:30, of laat beide leeg.');
      return;
    }
    save.mutate({ quiet_from: from.trim(), quiet_until: until.trim(), weekends_quiet: weekends });
  };

  return (
    <>
      <Page title="Meldingen" instanceName={instance?.name} spacing="sections">
        {query.isPending ? <Loading /> : null}
        {query.isError ? <ErrorNotice message={errorMessage(query.error)} /> : null}
        {saveError ? <ErrorNotice message={saveError} /> : null}
        {data && preference ? (
          <>
            <Section title="Op dit apparaat" level={2}>
              {!data.available ? (
                <EmptyNotice text="Meldingen zijn in deze omgeving niet ingesteld" />
              ) : (
                <Stack gap="related">
                  <Quiet>
                    Je krijgt een melding als er een taak op je wacht, als een taak over de datum is
                    en als er is beslist over een offerte van jou. Hooguit {data.daily_cap} per dag.
                    In een melding staat nooit een naam of een bedrag.
                  </Quiet>
                  {blocked ? <Quiet>{blocked}</Quiet> : null}
                  {error ? <ErrorNotice message={error} /> : null}
                  {state === 'off' ? (
                    <nldd-container layout="row" gap="8">
                      <Button
                        text="Zet meldingen aan"
                        appearance="primary"
                        onClick={() => void on()}
                        loading={busy}
                      />
                    </nldd-container>
                  ) : null}
                  {state === 'on' ? (
                    <nldd-container layout="row" gap="8" vertical-alignment="center">
                      <Button
                        text="Stuur een proefmelding"
                        onClick={() => {
                          setTested(false);
                          test.mutate();
                        }}
                        loading={test.isPending}
                      />
                      <Button
                        text="Zet uit op dit apparaat"
                        appearance="neutral-transparent"
                        onClick={() => void off()}
                        loading={busy}
                      />
                    </nldd-container>
                  ) : null}
                  {tested ? <Quiet>De proefmelding is onderweg.</Quiet> : null}
                </Stack>
              )}
            </Section>

            {data.devices.length > 0 ? (
              <Section title="Apparaten" level={2}>
                <nldd-table
                  accessible-label="Apparaten die meldingen krijgen"
                  columns={`minmax(180px,1fr) minmax(180px,1fr) ${ROW_ACTIONS_COLUMN}`}
                  sm-columns={`minmax(140px,1fr) ${ROW_ACTIONS_COLUMN}`}
                >
                  <nldd-table-row slot="header">
                    <nldd-text-cell text="Apparaat" />
                    <nldd-text-cell text="Gebruik" hide-below="md" />
                    <nldd-text-cell />
                  </nldd-table-row>
                  {data.devices.map((device) => (
                    <nldd-table-row key={device.id}>
                      <nldd-text-cell
                        text={device.id === here ? `${device.label} (dit apparaat)` : device.label}
                        supporting-text={`Aangezet op ${formatDate(device.created_at)}`}
                      />
                      <nldd-text-cell hide-below="md" text={usedText(device)} />
                      <RowActions
                        name={`apparaat ${device.label}`}
                        actions={[
                          {
                            text: 'Trek in',
                            destructive: true,
                            confirm: {
                              text: `Meldingen op '${device.label}' stoppen?`,
                              supportingText:
                                'Dit apparaat krijgt geen meldingen meer tot je ze daar weer aanzet.',
                              confirmText: 'Trek in',
                            },
                            onSelect: () => {
                              setSaveError(null);
                              if (device.id === here) void off();
                              else remove.mutate(device.id);
                            },
                          },
                        ]}
                      />
                    </nldd-table-row>
                  ))}
                </nldd-table>
              </Section>
            ) : null}

            <Section title="Waarover" level={2}>
              <Stack gap="related">
                <CheckboxInput
                  label="Er wacht een taak op mij"
                  checked={preference.tasks}
                  onChange={(checked) => change({ tasks: checked })}
                />
                <CheckboxInput
                  label="Een taak van mij is over de datum"
                  checked={preference.overdue}
                  onChange={(checked) => change({ overdue: checked })}
                />
                <CheckboxInput
                  label="Er is beslist over een offerte van mij"
                  checked={preference.decisions}
                  onChange={(checked) => change({ decisions: checked })}
                />
              </Stack>
            </Section>

            <Section title="Wanneer niet" level={2}>
              <Facts
                label="Stille uren"
                facts={[{ label: 'Stil', value: quietText(preference) }]}
              />
              <Quiet>Wat in die tijd binnenkomt, krijg je daarna in één melding.</Quiet>
              <nldd-container layout="row" gap="8">
                <Button text="Wijzig stille uren" onClick={editQuiet} />
              </nldd-container>
            </Section>
          </>
        ) : null}
      </Page>
      <FormSheet
        open={quietOpen}
        title="Stille uren"
        submitText="Bewaar"
        onSubmit={submitQuiet}
        onClose={() => setQuietOpen(false)}
        busy={save.isPending}
        error={quietError}
      >
        <FormFields>
          <TextInput label="Stil vanaf" value={from} onChange={setFrom} hint="Bijvoorbeeld 19:00" />
          <TextInput label="Stil tot" value={until} onChange={setUntil} hint="Bijvoorbeeld 07:30" />
          <CheckboxInput
            label="Ook stil in het weekend"
            checked={weekends}
            onChange={setWeekends}
          />
        </FormFields>
      </FormSheet>
    </>
  );
}
