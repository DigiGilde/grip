import { useState } from 'react';
import { ModelStatusSection } from '@/features/vacancies/ModelStatusSection';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { formatDate } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { OpenCell, OpenRow, ROW_ACTIONS_COLUMN, RowActions } from '@/ui/RowActions';
import { VACANCY_KEYS } from '@/features/vacancies/api';
import {
  Button,
  CheckboxInput,
  FileInput,
  Note,
  SelectInput,
  TextInput,
} from '@/features/vacancies/ui';
import {
  EmptyNotice,
  ErrorNotice,
  FormSheet,
  Loading,
  Page,
  Section,
  SectionHeading,
} from '@/ui/layout';
import {
  SETUP_KEYS,
  activateFormTemplate,
  fetchBundledMappings,
  fetchFormTemplates,
  fetchLanguageModel,
  inspectForm,
  uploadFormTemplate,
  type BundledMapping,
  type FormInspection,
  type FormTemplate,
  type TemplateSource,
} from './api';

const OWN_MAPPING = 'own';

function templateLine(template: FormTemplate): string {
  const parts = [
    template.file_name,
    `${template.mapped_fields} velden gekoppeld`,
    template.unverified_fields > 0
      ? `${template.unverified_fields} koppelingen niet gecontroleerd`
      : null,
    `aangeleverd op ${formatDate(template.created_at)}`,
    template.uploaded_by_name ? `door ${template.uploaded_by_name}` : null,
  ];
  return parts.filter(Boolean).join(' · ');
}

function Inspection({ inspection }: { inspection: FormInspection }) {
  return (
    <>
      <SectionHeading text="Velden in dit formulier" level={3} />
      <Note>
        Van elk veld de naam, het soort en waar het volgens de koppeling mee wordt gevuld. De inhoud
        van een veld wordt nooit getoond.
      </Note>
      {inspection.problem && <ErrorNotice message={inspection.problem} />}
      {inspection.missing_fields.length > 0 && (
        <Note>
          Velden uit de koppeling die niet in het formulier staan:{' '}
          {inspection.missing_fields.join(', ')}.
        </Note>
      )}
      <nldd-list accessible-label="Velden in het formulier">
        {inspection.fields.map((field) => (
          <nldd-list-item key={field.name} size="sm">
            <nldd-text-cell
              text={field.name}
              supporting-text={[
                field.type === 'checkbox' ? 'Selectievakje' : 'Tekstveld',
                field.label ?? field.source ?? 'niet gekoppeld',
                field.has_value ? 'is ingevuld' : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            />
          </nldd-list-item>
        ))}
      </nldd-list>
    </>
  );
}

function UploadSheet({
  open,
  onClose,
  mappings,
}: {
  open: boolean;
  onClose: () => void;
  mappings: BundledMapping[];
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('Aanvraagformulier vacature');
  const [choice, setChoice] = useState(mappings[0]?.name ?? OWN_MAPPING);
  const [mappingJson, setMappingJson] = useState('');
  const [clear, setClear] = useState(false);
  const [inspection, setInspection] = useState<FormInspection | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function source(): TemplateSource | null {
    if (!file) return null;
    return choice === OWN_MAPPING ? { file, mappingJson } : { file, bundledMapping: choice };
  }

  async function inspect() {
    const current = source();
    setProblem(null);
    if (!current) return setProblem('Kies eerst het lege formulier.');
    setBusy(true);
    try {
      setInspection(await inspectForm(current));
    } catch (caught) {
      setProblem(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    const current = source();
    setProblem(null);
    if (!current) return setProblem('Kies het lege formulier.');
    if (!name.trim()) return setProblem('Geef het formulier een naam.');
    if (choice === OWN_MAPPING && !mappingJson.trim()) {
      return setProblem('Lever een veldkoppeling aan, of kies een meegeleverde.');
    }
    setBusy(true);
    try {
      await uploadFormTemplate(current, name.trim(), clear);
      void queryClient.invalidateQueries({ queryKey: SETUP_KEYS.templates });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.options });
      void queryClient.invalidateQueries({ queryKey: ['vacancies', 'form-status'] });
      onClose();
    } catch (caught) {
      setProblem(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  const mappingOptions = [
    ...mappings.map((mapping) => ({ value: mapping.name, label: mapping.title })),
    { value: OWN_MAPPING, label: 'Eigen veldkoppeling' },
  ];

  return (
    <FormSheet
      open={open}
      title="Leeg aanvraagformulier aanleveren"
      submitText="Bewaar en gebruik dit formulier"
      onSubmit={() => void submit()}
      onClose={onClose}
      busy={busy}
      error={problem}
    >
      <Note>
        Het lege formulier van je organisatie, als invulbare pdf. Grip vult het per vacature in. Een
        formulier dat nog is ingevuld bevat namen en wordt geweigerd, tenzij je het eerst laat
        leegmaken.
      </Note>
      <FileInput
        label="Formulier (pdf)"
        accept=".pdf,application/pdf"
        onChange={(chosen) => {
          setFile(chosen);
          setInspection(null);
        }}
      />
      <TextInput label="Naam" value={name} onChange={setName} required />
      <SelectInput
        label="Veldkoppeling"
        hint="Welke gegevens uit grip in welk veld van het formulier komen."
        value={choice}
        onChange={(value) => {
          setChoice(value);
          setInspection(null);
        }}
        options={mappingOptions}
      />
      {choice === OWN_MAPPING && (
        <TextInput
          label="Eigen veldkoppeling (JSON)"
          hint="Dezelfde opbouw als een meegeleverde koppeling: per veld de naam, het soort en de bron."
          value={mappingJson}
          onChange={setMappingJson}
          multiline
          required
        />
      )}
      <CheckboxInput
        label="Maak het formulier eerst leeg als er nog iets is ingevuld"
        checked={clear}
        onChange={setClear}
      />
      <nldd-button-group>
        <Button text="Bekijk de velden" loading={busy} onClick={() => void inspect()} />
      </nldd-button-group>
      {inspection && <Inspection inspection={inspection} />}
    </FormSheet>
  );
}

function Templates() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [uploading, setUploading] = useState(false);
  const templates = useQuery({ queryKey: SETUP_KEYS.templates, queryFn: fetchFormTemplates });
  const mappings = useQuery({ queryKey: SETUP_KEYS.bundled, queryFn: fetchBundledMappings });
  const activate = useMutation({
    mutationFn: activateFormTemplate,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SETUP_KEYS.templates });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.options });
    },
  });

  const inUse = templates.data?.find((template) => template.is_active);
  const earlier = (templates.data ?? []).filter((template) => !template.is_active);
  const open = (template: FormTemplate) =>
    navigate(PATHS.formTemplate.replace(':templateId', template.id));

  return (
    <Section title="Aanvraagformulier">
      {templates.isPending && <Loading />}
      {templates.isError && <ErrorNotice message={errorMessage(templates.error)} />}
      {activate.isError && <ErrorNotice message={errorMessage(activate.error)} />}
      {templates.data && (
        <nldd-table
          accessible-label="Formulieren"
          columns={`minmax(260px,1fr) 140px ${ROW_ACTIONS_COLUMN}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Formulier" />
            <nldd-text-cell text="Stand" />
            <nldd-cell />
          </nldd-table-row>
          {[...(inUse ? [inUse] : []), ...earlier].map((template) => (
            <OpenRow key={template.id} onOpen={() => open(template)}>
              <OpenCell
                text={template.name}
                supportingText={templateLine(template)}
                accessibleLabel={`Bekijk het formulier ${template.name}`}
                onOpen={() => open(template)}
              />
              <nldd-cell>
                {template.is_active ? (
                  <nldd-tag color="success" text="In gebruik" />
                ) : (
                  <nldd-text color="secondary" size="sm">
                    Eerder gebruikt
                  </nldd-text>
                )}
              </nldd-cell>
              <nldd-cell>
                <RowActions
                  name={template.name}
                  actions={
                    template.is_active
                      ? [{ text: 'Vervang het formulier', onSelect: () => setUploading(true) }]
                      : [
                          {
                            text: 'Neem weer in gebruik',
                            onSelect: () => activate.mutate(template.id),
                          },
                        ]
                  }
                />
              </nldd-cell>
            </OpenRow>
          ))}
          <nldd-inline-dialog
            slot="empty"
            text="Nog geen formulier"
            supporting-text="Lever het lege aanvraagformulier van je organisatie aan om het per vacature te laten invullen."
          />
        </nldd-table>
      )}
      {templates.data && !inUse ? (
        <nldd-button-group>
          <Button
            text="Lever een leeg formulier aan"
            appearance="primary"
            onClick={() => setUploading(true)}
          />
        </nldd-button-group>
      ) : null}
      <UploadSheet
        // The mappings arrive after the first render; start the form with them.
        key={`upload-${mappings.data?.length ?? 0}-${templates.data?.length ?? 0}`}
        open={uploading}
        onClose={() => setUploading(false)}
        mappings={mappings.data ?? []}
      />
    </Section>
  );
}

function LanguageModelSection() {
  const [checked, setChecked] = useState(false);
  const model = useQuery({
    queryKey: [...SETUP_KEYS.model, checked],
    queryFn: () => fetchLanguageModel(checked),
  });

  return (
    <Section
      title="Taalmodel"
      description="Stelt concepten op van vacatureteksten. Adres, sleutel en model horen bij de omgeving en zijn hier niet te wijzigen."
    >
      {model.isPending && <Loading />}
      {model.isError && <ErrorNotice message={errorMessage(model.error)} />}
      {model.data && (
        <>
          <nldd-list appearance="box-base" accessible-label="Instellingen van het taalmodel">
            <nldd-list-item>
              <nldd-text-cell
                overline="Status"
                text={model.data.configured ? 'Ingesteld' : 'Niet ingesteld'}
                {...(model.data.missing_settings.length > 0
                  ? {
                      'supporting-text': `Ontbreekt: ${model.data.missing_settings.join(', ')}`,
                    }
                  : {})}
              />
            </nldd-list-item>
            {model.data.model_id && (
              <nldd-list-item>
                <nldd-text-cell overline="Model" text={model.data.model_id} />
              </nldd-list-item>
            )}
            <nldd-list-item>
              <nldd-text-cell
                overline="Omschrijving van de organisatie"
                text={model.data.organisation_description_set ? 'Ingesteld' : 'Niet ingesteld'}
                supporting-text="Gaat als context mee bij het opstellen van een concept."
              />
            </nldd-list-item>
          </nldd-list>
          {model.data.check_error && <ErrorNotice message={model.data.check_error} />}
          {model.data.available_models && (
            <Note>
              Modellen die dit adres aanbiedt: {model.data.available_models.join(', ') || 'geen'}.
            </Note>
          )}
          <nldd-spacer size="8" />
          <nldd-button-group>
            <Button
              text="Controleer de verbinding"
              loading={model.isFetching}
              onClick={() => (checked ? void model.refetch() : setChecked(true))}
            />
          </nldd-button-group>
        </>
      )}
    </Section>
  );
}

/** Beheer of what vacancies need: the blank request form and the language model. */
export function VacancySetupPage() {
  const instance = useInstance();
  // Asking for the templates tells whether the viewer manages them.
  const access = useQuery({
    queryKey: SETUP_KEYS.templates,
    queryFn: fetchFormTemplates,
    retry: false,
  });
  const denied = access.error instanceof ApiError && access.error.status === 403;

  return (
    <Page title="Vacatureformulier en taalmodel" instanceName={instance?.name} spacing="sections">
      {denied ? (
        <EmptyNotice
          text="Dit is voor beheerders"
          supportingText="Het aanvraagformulier en het taalmodel stelt een beheerder in."
        />
      ) : (
        <Templates />
      )}
      {!denied && !access.isPending ? <LanguageModelSection /> : null}
      {!denied && !access.isPending ? <ModelStatusSection /> : null}
    </Page>
  );
}
