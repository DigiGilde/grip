import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatDate } from '@/lib/format';
import { Button, DateInput, Note, SelectInput, TextInput } from '@/features/vacancies/ui';
import { ErrorNotice, FormSheet, Loading, SectionHeading, Stack } from '@/ui/layout';
import {
  FRAMEWORK_KEYS,
  createFunctionGroup,
  fetchFunctionFramework,
  parseScales,
  reloadFunctionFramework,
  updateFunctionGroup,
  type FunctionFamily,
  type FunctionGroup,
  type ReloadResult,
} from './api';

function groupLine(group: FunctionGroup): string {
  const parts = [
    group.scales_text,
    group.source === 'manual'
      ? 'zelf toegevoegd'
      : group.edited
        ? 'met de hand gewijzigd'
        : null,
    group.valid_to ? `beëindigd per ${formatDate(group.valid_to)}` : null,
  ];
  return parts.filter(Boolean).join(' · ');
}

function reloadSummary(result: ReloadResult): string {
  const changed = result.groups_created + result.groups_updated + result.families_created;
  const kept =
    result.groups_kept > 0
      ? ` ${result.groups_kept} met de hand gewijzigde functiegroepen zijn zo gelaten.`
      : '';
  if (changed === 0) return `De lijst is gelijk aan het referentiebestand.${kept}`;
  return `${result.groups_created} functiegroepen toegevoegd, ${result.groups_updated} bijgewerkt.${kept}`;
}

interface GroupSheetProps {
  families: FunctionFamily[];
  /** The group to correct, or null to add one. */
  group: FunctionGroup | null;
  open: boolean;
  onClose: () => void;
}

function GroupSheet({ families, group, open, onClose }: GroupSheetProps) {
  const queryClient = useQueryClient();
  const [familyId, setFamilyId] = useState(group?.family_id ?? families[0]?.id ?? '');
  const [name, setName] = useState(group?.name ?? '');
  const [scales, setScales] = useState(group ? group.scales.join(', ') : '');
  const [validTo, setValidTo] = useState(group?.valid_to ?? '');
  const [problem, setProblem] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (input: { family_id: string; name: string; scales: number[]; valid_to: string | null }) =>
      group
        ? updateFunctionGroup(group.id, input)
        : createFunctionGroup({ family_id: input.family_id, name: input.name, scales: input.scales }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['function-framework'] });
      onClose();
    },
  });

  function submit() {
    setProblem(null);
    const parsed = parseScales(scales);
    if (!name.trim()) return setProblem('Vul de naam van de functiegroep in.');
    if (!familyId) return setProblem('Kies de functiefamilie.');
    if (parsed === null) {
      return setProblem('Vul de schalen in als getallen van 1 tot en met 19, bijvoorbeeld 11, 12, 13.');
    }
    save.mutate({ family_id: familyId, name: name.trim(), scales: parsed, valid_to: validTo || null });
  }

  return (
    <FormSheet
      open={open}
      title={group ? `Functiegroep ${group.name} wijzigen` : 'Functiegroep toevoegen'}
      submitText="Bewaar"
      onSubmit={submit}
      onClose={onClose}
      busy={save.isPending}
      error={problem ?? (save.isError ? errorMessage(save.error) : null)}
    >
      {group && (
        <Note>
          Een vacature die deze functienaam al op het formulier heeft staan, houdt de naam van
          toen. Een gewijzigde groep wordt bij het opnieuw laden van het referentiebestand met
          rust gelaten.
        </Note>
      )}
      <SelectInput
        label="Functiefamilie"
        value={familyId}
        onChange={setFamilyId}
        options={families.map((family) => ({ value: family.id, label: family.name }))}
        required
      />
      <TextInput label="Functiegroep" value={name} onChange={setName} required />
      <TextInput
        label="Schalen"
        hint="Gescheiden door komma's, of als reeks: 11-13."
        value={scales}
        onChange={setScales}
        required
      />
      {group && (
        <DateInput
          label="Geldig tot en met"
          hint="Een beëindigde functiegroep is niet meer te kiezen bij een vacature."
          value={validTo}
          onChange={setValidTo}
          optional
        />
      )}
    </FormSheet>
  );
}

/** Beheer of the function families and groups a vacancy chooses from. */
export function FunctionFrameworkSection() {
  const queryClient = useQueryClient();
  const framework = useQuery({
    queryKey: FRAMEWORK_KEYS.all,
    queryFn: () => fetchFunctionFramework(true),
  });
  const [editing, setEditing] = useState<FunctionGroup | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const reload = useMutation({
    mutationFn: reloadFunctionFramework,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['function-framework'] }),
  });
  const families = framework.data?.families ?? [];
  const source = framework.data?.source;
  const groupCount = families.reduce((count, family) => count + family.groups.length, 0);

  return (
    <Stack gap="group">
      {source && (
        <Note>
          {groupCount} functiegroepen in {families.length} functiefamilies. Overgenomen van{' '}
          <a href={source.source_url} target="_blank" rel="noreferrer">
            de openbare pagina van het Functiegebouw Rijk
          </a>{' '}
          zoals die er op {formatDate(source.read_on)} stond. De site biedt de gegevens niet
          openbaar machineleesbaar aan; toegang tot de API is daar op aanvraag. Wijzigt het
          Functiegebouw, corrigeer dan hier of laad een nieuwer referentiebestand.
        </Note>
      )}
      <nldd-spacer size="8" />
      {framework.isPending && <Loading />}
      {framework.isError && <ErrorNotice message={errorMessage(framework.error)} />}
      {reload.isError && <ErrorNotice message={errorMessage(reload.error)} />}
      {reload.data && <nldd-banner variant="success" size="sm" text={reloadSummary(reload.data)} />}
      {families.map((family) => (
        <section key={family.id}>
          <nldd-spacer size="16" />
          <SectionHeading text={family.name} />
          <nldd-list appearance="box-base" accessible-label={`Functiegroepen in ${family.name}`}>
            {family.groups.map((group) => (
              <nldd-list-item key={group.id} size="sm">
                <nldd-text-cell text={group.name} supporting-text={groupLine(group)} />
                <nldd-spacer-cell size="8" />
                <nldd-cell>
                  <Button
                    text="Wijzig"
                    size="sm"
                    appearance="neutral-transparent"
                    accessibleLabel={`Wijzig de functiegroep ${group.name}`}
                    onClick={() => {
                      setEditing(group);
                      setSheetOpen(true);
                    }}
                  />
                </nldd-cell>
              </nldd-list-item>
            ))}
            <nldd-inline-dialog slot="empty" text="Nog geen functiegroepen in deze familie" />
          </nldd-list>
        </section>
      ))}
      <nldd-spacer size="16" />
      <nldd-button-group>
        <Button
          text="Voeg functiegroep toe"
          appearance="primary"
          onClick={() => {
            setEditing(null);
            setSheetOpen(true);
          }}
        />
        <Button
          text="Laad referentiebestand opnieuw"
          loading={reload.isPending}
          onClick={() => reload.mutate()}
        />
      </nldd-button-group>
      <GroupSheet
        // A fresh form per group and per saved state of it.
        key={`group-${editing?.id ?? 'new'}-${editing?.name ?? ''}-${editing?.scales.join('-') ?? ''}-${families.length}`}
        families={families}
        group={editing}
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
      />
    </Stack>
  );
}
