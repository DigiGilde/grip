import { ExternalLink, IconCell } from '@/ui/Icon';
import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { formatDate } from '@/lib/format';
import { Button, DateInput, SelectInput, TextInput } from '@/features/vacancies/ui';
import { EmptyNotice, ErrorNotice, FormSheet, Loading, Page, Quiet, Stack } from '@/ui/layout';
import {
  FRAMEWORK_KEYS,
  createFunctionGroup,
  fetchFunctionFramework,
  groupChoices,
  parseScales,
  reloadFunctionFramework,
  reloadSummary,
  scaleTag,
  searchGroups,
  updateFunctionGroup,
  type FunctionFamily,
  type FunctionGroup,
} from './api';

if (import.meta.env.MODE !== 'test') {
  void import('@nldd/design-system/search-field');
  void import('@nldd/design-system/tag');
}

/** What sets a group apart from the published list, if anything. */
function groupNote(group: FunctionGroup): string {
  return [
    group.source === 'manual' ? 'Zelf toegevoegd' : group.edited ? 'Met de hand gewijzigd' : null,
    group.valid_to ? `Beëindigd per ${formatDate(group.valid_to)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
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
    mutationFn: (input: {
      family_id: string;
      name: string;
      scales: number[];
      valid_to: string | null;
    }) =>
      group
        ? updateFunctionGroup(group.id, input)
        : createFunctionGroup({
            family_id: input.family_id,
            name: input.name,
            scales: input.scales,
          }),
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
      return setProblem(
        'Vul de schalen in als getallen van 1 tot en met 19, bijvoorbeeld 11, 12, 13.',
      );
    }
    save.mutate({
      family_id: familyId,
      name: name.trim(),
      scales: parsed,
      valid_to: validTo || null,
    });
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

interface GroupRowsProps {
  groups: (FunctionGroup & { family_name?: string })[];
  onEdit?: (group: FunctionGroup) => void;
  label: string;
}

/** Groups in aligned columns: name, scales as a tag, and a quiet way to change one. */
function GroupTable({ groups, onEdit, label }: GroupRowsProps) {
  const withFamily = groups.some((group) => group.family_name);
  const columns = [
    'minmax(240px,2fr)',
    ...(withFamily ? ['minmax(160px,1fr)'] : []),
    '120px',
    ...(onEdit ? ['100px'] : []),
  ].join(' ');
  return (
    <nldd-table accessible-label={label} columns={columns}>
      <nldd-table-row slot="header">
        <nldd-text-cell text="Functiegroep" />
        {withFamily && <nldd-text-cell text="Functiefamilie" />}
        <nldd-text-cell text="Schalen" />
        {onEdit && <nldd-text-cell text="" />}
      </nldd-table-row>
      {groups.map((group) => {
        const note = groupNote(group);
        return (
          <nldd-table-row key={group.id}>
            <nldd-text-cell text={group.name} {...(note ? { 'supporting-text': note } : {})} />
            {withFamily && <nldd-text-cell text={group.family_name ?? ''} />}
            <nldd-cell>
              <nldd-tag size="sm" color="neutral" text={scaleTag(group)} />
            </nldd-cell>
            {onEdit && (
              <nldd-cell>
                <Button
                  text="Wijzig"
                  size="sm"
                  appearance="neutral-transparent"
                  accessibleLabel={`Wijzig de functiegroep ${group.name}`}
                  onClick={() => onEdit(group)}
                />
              </nldd-cell>
            )}
          </nldd-table-row>
        );
      })}
    </nldd-table>
  );
}

// The chevron turns with the row; the attribute is not in the package's types yet.
const DISCLOSURE: object = { disclosure: '' };

interface FamilyRowProps {
  family: FunctionFamily;
  open: boolean;
  onToggle: () => void;
}

/** A family as one row that opens its groups; closed until asked. */
function FamilyRow({ family, open, onToggle }: FamilyRowProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onToggle);
  const count = family.groups.length;
  return (
    <nldd-list-item ref={ref} button expanded={orUndef(open)}>
      <IconCell concept="open" {...DISCLOSURE} />
      <nldd-spacer-cell size="8" />
      <nldd-text-cell text={family.name} />
      <nldd-text-cell
        width="fit-content"
        color="secondary"
        text={count === 1 ? '1 functiegroep' : `${count} functiegroepen`}
      />
    </nldd-list-item>
  );
}

interface ToolbarProps {
  query: string;
  onQuery: (value: string) => void;
  canManage: boolean;
  onAdd: () => void;
  onReload: () => void;
  reloading: boolean;
}

/** The search field on the left, the actions on the right, on one size. */
function Toolbar({ query, onQuery, canManage, onAdd, onReload, reloading }: ToolbarProps) {
  const searchRef = useRef<HTMLElement>(null);
  const addRef = useRef<HTMLElement>(null);
  const reloadRef = useRef<HTMLElement>(null);
  const addMenuRef = useRef<HTMLElement>(null);
  const reloadMenuRef = useRef<HTMLElement>(null);
  useNlddEvent(searchRef, 'input', (event) => {
    const detail = (event as CustomEvent<{ value?: string }>).detail;
    const target = event.target as { value?: string } | null;
    onQuery(detail?.value ?? target?.value ?? '');
  });
  useNlddEvent(addRef, 'click', onAdd);
  useNlddEvent(addMenuRef, 'select', onAdd);
  useNlddEvent(reloadRef, 'click', onReload);
  useNlddEvent(reloadMenuRef, 'select', onReload);
  return (
    <nldd-toolbar size="md" label="Zoeken in het Functiegebouw Rijk">
      <nldd-toolbar-item slot="start" priority={3}>
        <nldd-search-field
          ref={searchRef}
          size="md"
          width="360px"
          value={query}
          placeholder="Zoek op functiegroep of functiefamilie"
          accessible-label="Zoek op functiegroep of functiefamilie"
        />
      </nldd-toolbar-item>
      {canManage && (
        <>
          <nldd-toolbar-item slot="end" priority={1}>
            <nldd-button
              ref={reloadRef}
              size="md"
              appearance="secondary"
              text="Laad referentiebestand opnieuw"
              loading={orUndef(reloading)}
            />
            <nldd-menu-item
              ref={reloadMenuRef}
              slot="overflow"
              text="Laad referentiebestand opnieuw"
            />
          </nldd-toolbar-item>
          <nldd-toolbar-item slot="end" priority={2}>
            <nldd-button ref={addRef} size="md" appearance="primary" text="Voeg functiegroep toe" />
            <nldd-menu-item ref={addMenuRef} slot="overflow" text="Voeg functiegroep toe" />
          </nldd-toolbar-item>
        </>
      )}
    </nldd-toolbar>
  );
}

/**
 * The function families and groups a vacancy chooses from. Families are
 * closed until opened and a search goes over all groups, so the page fits a
 * screen however long the list is.
 */
export function FunctionFrameworkPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const framework = useQuery({
    queryKey: FRAMEWORK_KEYS.all,
    queryFn: () => fetchFunctionFramework(true),
  });
  const [query, setQuery] = useState('');
  const [openFamily, setOpenFamily] = useState<string | null>(null);
  const [editing, setEditing] = useState<FunctionGroup | null>(null);
  const [sheet, setSheet] = useState({ open: false, session: 0 });
  const reload = useMutation({
    mutationFn: reloadFunctionFramework,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['function-framework'] }),
  });
  const families = framework.data?.families ?? [];
  const source = framework.data?.source;
  const canManage = framework.data?.can_manage ?? false;
  const groupCount = families.reduce((count, family) => count + family.groups.length, 0);
  const searching = query.trim() !== '';
  const matches = searching ? searchGroups(groupChoices(framework.data), query) : [];

  function edit(group: FunctionGroup | null) {
    setEditing(group);
    setSheet((current) => ({ open: true, session: current.session + 1 }));
  }
  const onEdit = canManage ? (group: FunctionGroup) => edit(group) : undefined;

  return (
    <RouterLinks>
      <Page
        title="Functiegebouw Rijk"
        instanceName={instance?.name}
        back={{ href: PATHS.admin, text: 'Terug naar Beheer' }}
      >
        <Toolbar
          query={query}
          onQuery={setQuery}
          canManage={canManage}
          onAdd={() => edit(null)}
          onReload={() => reload.mutate()}
          reloading={reload.isPending}
        />
        {framework.isPending && <Loading />}
        {framework.isError && <ErrorNotice message={errorMessage(framework.error)} />}
        {reload.isError && <ErrorNotice message={errorMessage(reload.error)} />}
        {source && (
          <Stack gap="tight">
            <Quiet>
              {groupCount} functiegroepen in {families.length} functiefamilies, overgenomen van{' '}
              <ExternalLink inline href={source.source_url} text="functiegebouwrijksoverheid.nl" />{' '}
              op {formatDate(source.read_on)}
            </Quiet>
            {reload.data && <Quiet>{reloadSummary(reload.data)}</Quiet>}
          </Stack>
        )}
        {searching &&
          (matches.length > 0 ? (
            <GroupTable groups={matches} onEdit={onEdit} label="Gevonden functiegroepen" />
          ) : (
            <EmptyNotice text="Geen functiegroep gevonden" />
          ))}
        {!searching && families.length > 0 && (
          <Stack gap="related">
            <nldd-list appearance="box-base" accessible-label="Functiefamilies">
              {families.map((family) => (
                <FamilyRow
                  key={family.id}
                  family={family}
                  open={openFamily === family.id}
                  onToggle={() => setOpenFamily(openFamily === family.id ? null : family.id)}
                />
              ))}
            </nldd-list>
            {families
              .filter((family) => family.id === openFamily)
              .map((family) => (
                <GroupTable
                  key={family.id}
                  groups={family.groups}
                  onEdit={onEdit}
                  label={`Functiegroepen in ${family.name}`}
                />
              ))}
          </Stack>
        )}
        {canManage && (
          <GroupSheet
            // A fresh form each time the sheet opens.
            key={`group-${sheet.session}`}
            families={families}
            group={editing}
            open={sheet.open}
            onClose={() => setSheet((current) => ({ ...current, open: false }))}
          />
        )}
      </Page>
    </RouterLinks>
  );
}
