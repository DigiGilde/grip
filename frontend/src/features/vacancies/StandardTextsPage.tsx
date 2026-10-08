import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, errorMessage } from '@/api/client';
import { formatDate } from '@/lib/format';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { ActionBar } from '@/ui/ActionBar';
import { OpenCell, OpenRow, ROW_ACTIONS_COLUMN, RowActions, type RowAction } from '@/ui/RowActions';
import {
  EmptyNotice,
  ErrorNotice,
  Facts,
  FormSheet,
  Loading,
  Page,
  Quiet,
  Section,
  Stack,
} from '@/ui/layout';
import { StructuredText } from './StructuredText';
import {
  LIBRARY_KEY,
  addTemplate,
  changeSharedSection,
  changeTemplate,
  changeTextSettings,
  fetchLibrary,
  markTemplateRead,
  previewTemplate,
  setTemplateActive,
  type Library,
  type SharedSection,
  type StandardTemplate,
  type TemplateSection,
  type TextSettings,
} from './textWorkApi';
import { Button, TextInput } from './ui';

function useLibraryChange<Input>(change: (input: Input) => Promise<Library>, onDone?: () => void) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: change,
    onSuccess: (library) => {
      queryClient.setQueryData(LIBRARY_KEY, library);
      onDone?.();
    },
  });
  return {
    run: mutation.mutate,
    busy: mutation.isPending,
    error: mutation.isError ? errorMessage(mutation.error) : null,
  };
}

function scales(template: StandardTemplate): string {
  if (template.scale_min && template.scale_max && template.scale_min !== template.scale_max) {
    return `${template.scale_min} t/m ${template.scale_max}`;
  }
  return String(template.scale_min ?? template.scale_max ?? '');
}

function parseScale(input: string): number | null {
  const value = Number(input.trim());
  return input.trim() && Number.isInteger(value) && value >= 1 && value <= 19 ? value : null;
}

function TemplateSheet({
  library,
  template,
  copyOf,
  onClose,
}: {
  library: Library;
  template: StandardTemplate | null;
  copyOf: StandardTemplate | null;
  onClose: () => void;
}) {
  const source = template ?? copyOf;
  const [role, setRole] = useState(template?.role_name ?? '');
  const [aliases, setAliases] = useState((template?.aliases ?? []).join(', '));
  const [low, setLow] = useState(String(source?.scale_min ?? ''));
  const [high, setHigh] = useState(String(source?.scale_max ?? ''));
  const [group, setGroup] = useState(source?.function_group ?? '');
  const [sections, setSections] = useState<TemplateSection[]>(
    source?.sections ?? [
      { key: 'intro', heading: '', body: '' },
      { key: 'dit_ga_je_doen', heading: 'Dit ga je doen', body: '' },
      { shared: 'dit_krijg_je' },
      { shared: 'dit_bieden_we' },
      { key: 'dit_vragen_wij', heading: 'Dit vragen wij', body: '' },
      { shared: 'hier_kom_je_te_werken' },
      { shared: 'bijzonderheden' },
      { shared: 'iedereen_welkom' },
    ],
  );
  const [problem, setProblem] = useState<string | null>(null);
  const shared = new Map(library.shared_sections.map((section) => [section.key, section]));
  const change = useLibraryChange(() => {
    const body = {
      role_name: role.trim(),
      aliases: aliases
        .split(',')
        .map((alias) => alias.trim())
        .filter(Boolean),
      scale_min: parseScale(low),
      scale_max: parseScale(high),
      function_group: group.trim() || null,
      sections: sections.filter((section) => section.shared || section.body?.trim()),
    };
    return template ? changeTemplate(template.id, body) : addTemplate(body);
  }, onClose);

  return (
    <FormSheet
      open
      size="wide"
      title={template ? `Standaardtekst ${template.role_name}` : 'Nieuwe standaardtekst'}
      submitText="Bewaar"
      onSubmit={() => {
        setProblem(null);
        if (!role.trim()) return setProblem('Geef de rol waarvoor de tekst is.');
        change.run(undefined);
      }}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      <TextInput label="Rol" value={role} onChange={setRole} required />
      <TextInput
        label="Andere namen voor deze rol"
        hint="Gescheiden door een komma. Een vacature met zo'n functienaam krijgt deze tekst."
        value={aliases}
        onChange={setAliases}
        optional
      />
      <TextInput label="Laagste schaal" value={low} onChange={setLow} keyboard="numeric" optional />
      <TextInput
        label="Hoogste schaal"
        value={high}
        onChange={setHigh}
        keyboard="numeric"
        optional
      />
      <TextInput label="Functiegroep" value={group} onChange={setGroup} optional />
      {sections.map((section, index) => {
        if (section.shared) {
          const own = shared.get(section.shared);
          return (
            <Quiet key={`shared-${section.shared}`}>
              Gedeeld onderdeel: {own?.heading ?? section.shared}. Wijzigen doe je bij de gedeelde
              onderdelen.
            </Quiet>
          );
        }
        return (
          <TextInput
            key={section.key ?? index}
            label={section.heading || 'Inleiding'}
            value={section.body ?? ''}
            onChange={(body) =>
              setSections((current) =>
                current.map((item, at) => (at === index ? { ...item, body } : item)),
              )
            }
            multiline
          />
        );
      })}
      <Quiet>
        Tussen accolades vult de vacature in:{' '}
        {library.placeholders.map((placeholder) => `{${placeholder.name}}`).join(', ')}.
      </Quiet>
    </FormSheet>
  );
}

function SharedSheet({ section, onClose }: { section: SharedSection; onClose: () => void }) {
  const [heading, setHeading] = useState(section.heading);
  const [body, setBody] = useState(section.body);
  const change = useLibraryChange(
    () => changeSharedSection(section.key, heading.trim(), body.trim()),
    onClose,
  );
  return (
    <FormSheet
      open
      size="wide"
      title={`Gedeeld onderdeel: ${section.heading}`}
      submitText="Bewaar voor alle rollen"
      onSubmit={() => change.run(undefined)}
      onClose={onClose}
      busy={change.busy}
      error={change.error}
    >
      <TextInput label="Kop" value={heading} onChange={setHeading} required />
      <TextInput label="Tekst" value={body} onChange={setBody} multiline required />
      <Quiet>
        Staat in de standaardtekst van {section.used_by.length}{' '}
        {section.used_by.length === 1 ? 'rol' : 'rollen'}: {section.used_by.join(', ')}.
      </Quiet>
    </FormSheet>
  );
}

function SettingsSheet({ settings, onClose }: { settings: TextSettings; onClose: () => void }) {
  const [values, setValues] = useState(settings);
  const change = useLibraryChange(() => changeTextSettings(values), onClose);
  const field = (name: keyof TextSettings) => (value: string) =>
    setValues((current) => ({ ...current, [name]: value }));
  return (
    <FormSheet
      open
      title="Wat de teksten invullen"
      submitText="Bewaar"
      onSubmit={() => change.run(undefined)}
      onClose={onClose}
      busy={change.busy}
      error={change.error}
    >
      <TextInput
        label="Naam van het onderdeel"
        hint="Zoals het in een zin staat, bijvoorbeeld met het lidwoord erbij."
        value={values.unit_name}
        onChange={field('unit_name')}
        optional
      />
      <TextInput
        label="Standplaats"
        value={values.location}
        onChange={field('location')}
        optional
      />
      <TextInput
        label="Website"
        value={values.website}
        onChange={field('website')}
        keyboard="url"
        optional
      />
      <TextInput
        label="Bij wie een sollicitant terecht kan"
        hint="Een algemeen adres of een functie. Dit staat in elke vacaturetekst."
        value={values.contact}
        onChange={field('contact')}
        optional
      />
    </FormSheet>
  );
}

function PreviewSheet({ template, onClose }: { template: StandardTemplate; onClose: () => void }) {
  const preview = useQuery({
    queryKey: ['vacancy-texts', 'preview', template.id, template.changed_at],
    queryFn: () => previewTemplate(template.id),
  });
  return (
    <FormSheet
      open
      size="wide"
      title={`${template.role_name} als voorbeeld`}
      submitText="Sluit"
      onSubmit={onClose}
      onClose={onClose}
    >
      {preview.isPending && <Loading />}
      {preview.isError && <ErrorNotice message={errorMessage(preview.error)} />}
      {preview.data && (
        <Stack gap="group">
          {preview.data.missing.length > 0 && (
            <Quiet>Een vacature moet nog aanvullen: {preview.data.missing.join(', ')}.</Quiet>
          )}
          <StructuredText text={preview.data.text} />
        </Stack>
      )}
    </FormSheet>
  );
}

type Sheet =
  | { kind: 'template'; template: StandardTemplate | null; copyOf: StandardTemplate | null }
  | { kind: 'shared'; section: SharedSection }
  | { kind: 'settings' }
  | { kind: 'preview'; template: StandardTemplate };

/** The standard vacancy texts of the organisation, per role. */
export function StandardTextsPage() {
  const instance = useInstance();
  const library = useQuery({ queryKey: LIBRARY_KEY, queryFn: fetchLibrary, retry: false });
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [opened, setOpened] = useState(0);
  const read = useLibraryChange((id: string) => markTemplateRead(id));
  const active = useLibraryChange((input: { id: string; on: boolean }) =>
    setTemplateActive(input.id, input.on),
  );
  const open = (next: Sheet) => {
    setOpened((count) => count + 1);
    setSheet(next);
  };
  const close = () => setSheet(null);
  const denied = library.error instanceof ApiError && library.error.status === 403;
  const data = library.data;
  const manage = data?.may_manage ?? false;

  const unread = data?.templates.filter(
    (template) => template.is_active && template.status === 'derived_unread',
  ).length;

  return (
    <RouterLinks>
      <Page
        title="Standaardteksten voor vacatures"
        instanceName={instance?.name}
        spacing="sections"
        back={{ href: PATHS.admin, text: 'Terug naar Beheer' }}
      >
        {library.isPending && <Loading />}
        {denied && <EmptyNotice text="Dit is voor wie vacatures maakt" />}
        {library.isError && !denied && <ErrorNotice message={errorMessage(library.error)} />}
        {data && (
          <>
            <Stack gap="related">
              {manage && (
                <ActionBar
                  label="Standaardteksten beheren"
                  actions={[
                    {
                      text: 'Nieuwe standaardtekst',
                      onClick: () => open({ kind: 'template', template: null, copyOf: null }),
                      primary: true,
                    },
                  ]}
                />
              )}
              {(read.error ?? active.error) && (
                <ErrorNotice message={read.error ?? active.error ?? ''} />
              )}
              {manage && unread ? (
                <nldd-text>
                  {unread === 1
                    ? 'Eén tekst is afgeleid en nog niet nagelezen.'
                    : `${unread} teksten zijn afgeleid en nog niet nagelezen.`}
                </nldd-text>
              ) : null}
            </Stack>
            <Section title="Per rol">
              <nldd-table
                accessible-label="Standaardteksten per rol"
                columns={`minmax(200px,2fr) 110px minmax(200px,1.4fr) ${ROW_ACTIONS_COLUMN}`}
                sm-columns={`minmax(160px,1fr) ${ROW_ACTIONS_COLUMN}`}
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Rol" />
                  <nldd-text-cell text="Schaal" hide-below="md" />
                  <nldd-text-cell text="Stand" hide-below="md" />
                  <nldd-cell />
                </nldd-table-row>
                {data.templates.map((template) => {
                  const actions: RowAction[] = [
                    {
                      text: 'Bekijk als voorbeeld',
                      onSelect: () => open({ kind: 'preview', template }),
                    },
                  ];
                  if (manage) {
                    if (template.status === 'derived_unread') {
                      actions.push({
                        text: 'Markeer als nagelezen',
                        onSelect: () => read.run(template.id),
                      });
                    }
                    actions.push({
                      text: 'Kopieer naar een nieuwe rol',
                      onSelect: () => open({ kind: 'template', template: null, copyOf: template }),
                    });
                    actions.push({
                      text: template.is_active ? 'Schakel uit' : 'Schakel in',
                      onSelect: () => active.run({ id: template.id, on: !template.is_active }),
                    });
                  }
                  const onOpen = () =>
                    open(
                      manage
                        ? { kind: 'template', template, copyOf: null }
                        : { kind: 'preview', template },
                    );
                  const changed = template.changed_at
                    ? `${template.changed_by_name ?? 'Gewijzigd'} op ${formatDate(template.changed_at)}`
                    : '';
                  return (
                    <OpenRow key={template.id} onOpen={onOpen}>
                      <OpenCell
                        text={template.role_name}
                        {...(template.aliases.length > 0
                          ? { supportingText: `Ook: ${template.aliases.join(', ')}` }
                          : {})}
                        accessibleLabel={`${manage ? 'Wijzig' : 'Bekijk'} de standaardtekst voor ${template.role_name}`}
                        onOpen={onOpen}
                      />
                      <nldd-text-cell text={scales(template)} hide-below="md" />
                      {/* Only what asks something gets a label; a text taken from
                        the examples as it was says nothing here. */}
                      <nldd-cell hide-below="md">
                        {!template.is_active ? (
                          <nldd-tag color="neutral" text="Uitgeschakeld" />
                        ) : template.status === 'derived_unread' ? (
                          <nldd-tag color="warning" text="Nog nalezen" />
                        ) : (
                          <nldd-text color="secondary" size="sm">
                            {changed}
                          </nldd-text>
                        )}
                      </nldd-cell>
                      <RowActions name={template.role_name} actions={actions} />
                    </OpenRow>
                  );
                })}
                <nldd-inline-dialog slot="empty" text="Nog geen standaardteksten" />
              </nldd-table>
            </Section>
            <Section title="Gedeelde onderdelen">
              <nldd-table
                accessible-label="Onderdelen die in elke standaardtekst staan"
                columns="minmax(200px,2fr) minmax(200px,1.4fr)"
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Onderdeel" />
                  <nldd-text-cell text="Gebruikt in" />
                </nldd-table-row>
                {data.shared_sections.map((section) => (
                  <OpenRow
                    key={section.key}
                    onOpen={manage ? () => open({ kind: 'shared', section }) : undefined}
                  >
                    <OpenCell
                      text={section.heading}
                      {...(section.changed_at
                        ? {
                            supportingText: `${section.changed_by_name ?? 'Gewijzigd'} op ${formatDate(section.changed_at)}`,
                          }
                        : {})}
                      {...(manage
                        ? {
                            accessibleLabel: `Wijzig het gedeelde onderdeel ${section.heading}`,
                            onOpen: () => open({ kind: 'shared', section }),
                          }
                        : {})}
                    />
                    <nldd-text-cell
                      text={`${section.used_by.length} ${section.used_by.length === 1 ? 'rol' : 'rollen'}`}
                    />
                  </OpenRow>
                ))}
              </nldd-table>
            </Section>
            <Section title="Wat de teksten invullen">
              <Facts
                label="Gegevens die een standaardtekst invult"
                facts={[
                  { label: 'Naam van het onderdeel', value: data.settings.unit_name },
                  { label: 'Standplaats', value: data.settings.location },
                  { label: 'Website', value: data.settings.website },
                  { label: 'Bij wie een sollicitant terecht kan', value: data.settings.contact },
                ]}
              />
              {manage && (
                <nldd-button-group>
                  <Button text="Wijzig" onClick={() => open({ kind: 'settings' })} />
                </nldd-button-group>
              )}
            </Section>
            {sheet?.kind === 'template' && (
              <TemplateSheet
                key={opened}
                library={data}
                template={sheet.template}
                copyOf={sheet.copyOf}
                onClose={close}
              />
            )}
            {sheet?.kind === 'shared' && (
              <SharedSheet key={opened} section={sheet.section} onClose={close} />
            )}
            {sheet?.kind === 'settings' && (
              <SettingsSheet key={opened} settings={data.settings} onClose={close} />
            )}
            {sheet?.kind === 'preview' && (
              <PreviewSheet key={opened} template={sheet.template} onClose={close} />
            )}
          </>
        )}
      </Page>
    </RouterLinks>
  );
}
