import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { Button, SelectInput, TextInput } from '@/features/assignments/ui';
import {
  approvalKeys,
  fetchInstanceSettings,
  saveInstanceSettings,
  type InstanceSetting,
} from '@/features/quotes/approval';
import { useAdminBack } from '@/layout/useAdminBack';
import { useInstance } from '@/layout/useInstance';
import { FOR_BEHEERDERS } from '@/pages/AdminOnly';
import { ConflictPanel } from '@/ui/ConflictPanel';
import { Facts, FormSheet, LoadError, Loading, Page, Section, type Fact } from '@/ui/layout';
import { SETTINGS_KEY, useStaleChoice } from '@/ui/stale';
import {
  CASE_CHOICES,
  MAX_DAYS,
  MAX_YEARS,
  SETTING_ASSIGNMENT,
  SETTING_CLOSE_AFTER_PROPOSAL,
  SETTING_EVENTS,
  SETTING_PROPOSE_CLOSE,
  SETTING_READS,
  SETTING_REQUEST_FORMS,
  caseRuleOf,
  caseRuleText,
  choiceOf,
  closeAfterProposalText,
  eventsText,
  inputOf,
  proposeCloseText,
  requestFormsText,
  wholeNumber,
  type CaseChoice,
} from './retention';

type Sheet = 'assignment' | 'dossier' | 'data';

// One width for the three lists, so their values share a left edge.
const LABEL_WIDTH = '280px';

function find(items: readonly InstanceSetting[], key: string): InstanceSetting | undefined {
  return items.find((item) => item.key === key);
}

/** How long the instance keeps what, and what happens after. For the beheerder. */
export function RetentionPage() {
  const instance = useInstance();
  const adminBack = useAdminBack();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: approvalKeys.settings,
    queryFn: fetchInstanceSettings,
    retry: false,
  });
  const items = query.data?.items ?? [];
  // Each part shows only the settings the server lists.
  const assignment = find(items, SETTING_ASSIGNMENT);
  const proposeClose = find(items, SETTING_PROPOSE_CLOSE);
  const closeAfterProposal = find(items, SETTING_CLOSE_AFTER_PROPOSAL);
  const events = find(items, SETTING_EVENTS);
  const reads = find(items, SETTING_READS);
  const requestForms = find(items, SETTING_REQUEST_FORMS);
  const rule = caseRuleOf(assignment?.value);

  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState<CaseChoice>('none');
  const [years, setYears] = useState('');
  const [nextPropose, setNextPropose] = useState('');
  const [nextClose, setNextClose] = useState('');
  const [nextEvents, setNextEvents] = useState('');
  const [nextReads, setNextReads] = useState('');
  const [nextForms, setNextForms] = useState('');

  // The settings are saved together, so they share one version. A sheet
  // saves on the version it was opened on.
  const stale = useStaleChoice(
    SETTINGS_KEY,
    query.data?.settings_version,
    () => queryClient.invalidateQueries({ queryKey: approvalKeys.settings }),
    sheet,
  );
  const [sent, setSent] = useState<Record<string, unknown>>({});
  const save = useMutation({
    mutationFn: ({ values, onTop }: { values: Record<string, unknown>; onTop?: boolean }) =>
      saveInstanceSettings(values, onTop ? stale.latestHeaders : stale.headers),
    onMutate: ({ values }) => setSent(values),
    onSuccess: (saved) => {
      stale.saved(saved.settings_version);
      queryClient.setQueryData(approvalKeys.settings, saved);
      setSheet(null);
    },
    onError: async (failure) => {
      if (!(await stale.caught(failure))) setError(errorMessage(failure));
    },
  });
  const conflictPanel = stale.conflict ? (
    <ConflictPanel
      conflict={stale.conflict}
      busy={save.isPending}
      onKeepMine={() => save.mutate({ values: sent, onTop: true })}
      onTakeTheirs={() => {
        stale.clear();
        setSheet(null);
      }}
    />
  ) : null;

  const open = (which: Sheet) => {
    setChoice(choiceOf(rule));
    setYears(rule?.outcome === 'destroy' ? String(rule.years) : '');
    setNextPropose(inputOf(proposeClose?.value));
    setNextClose(inputOf(closeAfterProposal?.value));
    setNextEvents(inputOf(events?.value));
    setNextReads(inputOf(reads?.value));
    setNextForms(inputOf(requestForms?.value));
    setError(null);
    setSheet(which);
  };

  const submit = (values: Record<string, unknown> | string) => {
    if (typeof values === 'string') {
      setError(values);
      return;
    }
    setError(null);
    save.mutate({ values });
  };

  const assignmentValues = (): Record<string, unknown> | string => {
    if (choice === 'keep') return { [SETTING_ASSIGNMENT]: { outcome: 'keep' } };
    if (choice === 'none') return { [SETTING_ASSIGNMENT]: null };
    const count = wholeNumber(years, 1, MAX_YEARS);
    if (count === null) return `Vul een heel aantal jaren in, van 1 tot en met ${MAX_YEARS}.`;
    return { [SETTING_ASSIGNMENT]: { outcome: 'destroy', years: count } };
  };

  const dossierValues = (): Record<string, unknown> | string => {
    const values: Record<string, unknown> = {};
    for (const [setting, input, name] of [
      [proposeClose, nextPropose, 'de taak om te sluiten'],
      [closeAfterProposal, nextClose, 'vanzelf sluiten'],
    ] as const) {
      if (!setting) continue;
      if (input.trim() === '') {
        values[setting.key] = null;
        continue;
      }
      const count = wholeNumber(input, 0, MAX_DAYS);
      if (count === null) {
        return `Vul bij ${name} een heel aantal dagen in, van 0 tot en met ${MAX_DAYS}, of laat het leeg.`;
      }
      values[setting.key] = count;
    }
    return values;
  };

  const dataValues = (): Record<string, unknown> | string => {
    const values: Record<string, unknown> = {};
    for (const [setting, input, name] of [
      [events, nextEvents, 'gebeurtenissen'],
      [reads, nextReads, 'wie wat inzag'],
      [requestForms, nextForms, 'aanvraagformulieren'],
    ] as const) {
      if (!setting) continue;
      const count = wholeNumber(input, 0, MAX_DAYS);
      if (count === null) {
        return `Vul bij ${name} een heel aantal dagen in, van 0 tot en met ${MAX_DAYS}.`;
      }
      values[setting.key] = count;
    }
    return values;
  };

  const dossierFacts: Fact[] = [
    ...(proposeClose
      ? [{ label: 'Taak om het dossier te sluiten', value: proposeCloseText(proposeClose.value) }]
      : []),
    ...(closeAfterProposal
      ? [
          {
            label: 'Grip sluit het dossier',
            value: closeAfterProposalText(closeAfterProposal.value),
          },
        ]
      : []),
  ];
  const dataFacts: Fact[] = [
    ...(events
      ? [{ label: 'Gebeurtenissen buiten een opdracht', value: eventsText(events.value) }]
      : []),
    ...(reads ? [{ label: 'Wie wat inzag', value: eventsText(reads.value) }] : []),
    ...(requestForms
      ? [
          {
            label: 'Aanvraagformulieren van vacatures',
            value: requestFormsText(requestForms.value),
          },
        ]
      : []),
  ];

  return (
    <>
      <Page
        kind="document"
        title="Bewaartermijnen"
        instanceName={instance?.name}
        spacing="sections"
        back={adminBack}
      >
        {query.isPending ? <Loading /> : null}
        {query.isError ? (
          <LoadError error={query.error} retry={() => void query.refetch()} who={FOR_BEHEERDERS} />
        ) : null}
        {query.data && assignment ? (
          <Section title="Opdrachten" level={2}>
            <Facts
              label="Bewaartermijn van opdrachten"
              facts={[{ label: 'Na het sluiten van het dossier', value: caseRuleText(rule) }]}
              labelWidth={LABEL_WIDTH}
            />
            <nldd-button-group>
              <Button text="Wijzig" onClick={() => open('assignment')} />
            </nldd-button-group>
          </Section>
        ) : null}
        {query.data && dossierFacts.length > 0 ? (
          <Section title="Dossiers sluiten" level={2}>
            <Facts
              label="Wanneer een dossier sluit"
              facts={dossierFacts}
              labelWidth={LABEL_WIDTH}
            />
            <nldd-button-group>
              <Button text="Wijzig" onClick={() => open('dossier')} />
            </nldd-button-group>
          </Section>
        ) : null}
        {query.data && dataFacts.length > 0 ? (
          <Section title="Per soort gegeven" level={2}>
            <Facts
              label="Bewaartermijnen per soort gegeven"
              facts={dataFacts}
              labelWidth={LABEL_WIDTH}
            />
            <nldd-button-group>
              <Button text="Wijzig" onClick={() => open('data')} />
            </nldd-button-group>
          </Section>
        ) : null}
      </Page>

      <FormSheet
        open={sheet === 'assignment'}
        title="Bewaartermijn van opdrachten wijzigen"
        submitText="Bewaar"
        busy={save.isPending}
        error={sheet === 'assignment' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => submit(assignmentValues())}
      >
        {conflictPanel}
        <nldd-text>
          <p>
            Volg de selectielijst van de organisatie. De termijn loopt vanaf de dag dat het dossier
            is gesloten.
          </p>
        </nldd-text>
        <SelectInput
          label="Na het sluiten van het dossier"
          value={choice}
          onChange={(value) => setChoice(value as CaseChoice)}
          options={CASE_CHOICES}
          required
        />
        {choice === 'destroy' ? (
          <TextInput
            label="Aantal jaren"
            hint={`Van 1 tot en met ${MAX_YEARS}`}
            keyboard="numeric"
            value={years}
            onChange={setYears}
            required
          />
        ) : null}
      </FormSheet>

      <FormSheet
        open={sheet === 'dossier'}
        title="Dossiers sluiten wijzigen"
        submitText="Bewaar"
        busy={save.isPending}
        error={sheet === 'dossier' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => submit(dossierValues())}
      >
        {conflictPanel}
        {proposeClose ? (
          <TextInput
            label="Taak om het dossier te sluiten, na zoveel dagen zonder wijziging"
            hint="In dagen. Leeg is nooit."
            keyboard="numeric"
            value={nextPropose}
            onChange={setNextPropose}
            optional
          />
        ) : null}
        {closeAfterProposal ? (
          <TextInput
            label="Grip sluit het dossier, zoveel dagen na die taak"
            hint="In dagen. Leeg is nooit."
            keyboard="numeric"
            value={nextClose}
            onChange={setNextClose}
            optional
          />
        ) : null}
      </FormSheet>

      <FormSheet
        open={sheet === 'data'}
        title="Bewaartermijnen per soort gegeven wijzigen"
        submitText="Bewaar"
        busy={save.isPending}
        error={sheet === 'data' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => submit(dataValues())}
      >
        {conflictPanel}
        {events ? (
          <TextInput
            label="Gebeurtenissen buiten een opdracht"
            hint="Dagen tot de waarden worden gewist. 0 is nooit."
            keyboard="numeric"
            value={nextEvents}
            onChange={setNextEvents}
            required
          />
        ) : null}
        {reads ? (
          <TextInput
            label="Wie wat inzag"
            hint="Dagen tot het wordt gewist. 0 is nooit."
            keyboard="numeric"
            value={nextReads}
            onChange={setNextReads}
            required
          />
        ) : null}
        {requestForms ? (
          <TextInput
            label="Aanvraagformulieren van vacatures"
            hint="Dagen na het vervullen, intrekken of afwijzen. 0 is bij de eerstvolgende ronde."
            keyboard="numeric"
            value={nextForms}
            onChange={setNextForms}
            required
          />
        ) : null}
      </FormSheet>
    </>
  );
}
