import { DocumentLink } from '@/ui/Icon';
import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { VACANCY_KEYS, fetchVacancies } from '@/features/vacancies/api';
import { SelectInput } from '@/features/vacancies/ui';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PATHS } from '@/paths';
import { OpenCell, OpenRow } from '@/ui/RowActions';
import {
  EmptyNotice,
  ErrorNotice,
  FilterSelect,
  FormSheet,
  Loading,
  Page,
  Section,
} from '@/ui/layout';
import {
  fetchTemplateDetail,
  setTemplateField,
  templateFileUrl,
  templateKey,
  templateSampleUrl,
  type FieldSource,
  type TemplateDetail,
  type TemplateField,
} from './api';

const EXAMPLE = 'example';
const NOTHING = 'nothing';

/** The name a reader knows the field by: its caption on the form, else its name. */
const fieldName = (field: TemplateField) => field.label || field.name;

function stateText(field: TemplateField): string {
  if (field.state === 'missing') return 'Staat niet meer in het formulier';
  if (field.state === 'unfilled') return 'Grip vult dit niet in';
  return field.fills ?? '';
}

/** Sources a field of this kind can take: a tick box needs a source with choices. */
function sourcesFor(field: TemplateField, sources: readonly FieldSource[]): FieldSource[] {
  return sources.filter((source) =>
    field.type === 'checkbox' ? source.choices.length > 0 : source.choices.length === 0,
  );
}

interface FieldSheetProps {
  detail: TemplateDetail;
  field: TemplateField | null;
  onClose: () => void;
}

function FieldSheet({ detail, field, onClose }: FieldSheetProps) {
  const queryClient = useQueryClient();
  const [source, setSource] = useState(field?.source ?? NOTHING);
  const [choice, setChoice] = useState(field?.equals === undefined ? '' : String(field?.equals));
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (change: { source: string | null; equals?: string | boolean | null }) =>
      setTemplateField(detail.id, field?.name ?? '', change),
    onSuccess: (saved) => {
      queryClient.setQueryData(templateKey(detail.id), saved);
      onClose();
    },
    onError: (failure) => setError(errorMessage(failure)),
  });
  const options = field ? sourcesFor(field, detail.sources) : [];
  const chosen = options.find((item) => item.key === source);
  const gone = field?.state === 'missing';

  const submit = () => {
    if (source === NOTHING || gone) {
      save.mutate({ source: null });
      return;
    }
    if (chosen && chosen.choices.length > 0) {
      const picked = chosen.choices.find((item) => String(item.value) === choice);
      if (!picked) {
        setError('Kies bij welke waarde het vakje wordt aangevinkt.');
        return;
      }
      save.mutate({ source, equals: picked.value });
      return;
    }
    save.mutate({ source });
  };

  return (
    <FormSheet
      open={field !== null}
      title={field ? `${fieldName(field)} koppelen` : 'Veld koppelen'}
      submitText={gone ? 'Haal de koppeling weg' : 'Bewaar'}
      busy={save.isPending}
      error={error}
      onClose={onClose}
      onSubmit={submit}
    >
      {gone ? (
        <nldd-text>
          Dit veld staat in de koppeling, maar niet meer in het formulier. Er wordt niets mee
          ingevuld.
        </nldd-text>
      ) : (
        <>
          <SelectInput
            label="Grip vult hier in"
            value={source}
            onChange={(value) => {
              setSource(value);
              setChoice('');
              setError(null);
            }}
            options={[
              { value: NOTHING, label: 'Niets: het veld blijft leeg' },
              ...options.map((item) => ({ value: item.key, label: item.label })),
            ]}
          />
          {chosen && chosen.choices.length > 0 ? (
            <SelectInput
              label="Aangevinkt bij"
              value={choice}
              onChange={setChoice}
              placeholder="Kies een waarde"
              options={chosen.choices.map((item) => ({
                value: String(item.value),
                label: item.label,
              }))}
              required
            />
          ) : null}
        </>
      )}
    </FormSheet>
  );
}

/** One stored form: the blank file, a filled sample, and what fills each field. */
export function FormTemplatePage() {
  const { templateId = '' } = useParams();
  const instance = useInstance();
  const containerRef = useRef<HTMLDivElement>(null);
  useRouterLinks(containerRef);
  const detail = useQuery({
    queryKey: templateKey(templateId),
    queryFn: () => fetchTemplateDetail(templateId),
    retry: false,
  });
  const vacancies = useQuery({ queryKey: VACANCY_KEYS.list, queryFn: fetchVacancies });
  const [picked, setPicked] = useState<string | null>(null);
  const [editing, setEditing] = useState<TemplateField | null>(null);

  // The most recent vacancy by default: what a requester would get today.
  const recent = vacancies.data?.[0]?.id;
  const sampleOf = picked ?? recent ?? EXAMPLE;
  const denied = detail.error instanceof ApiError && detail.error.status === 403;
  const data = detail.data;

  return (
    <div ref={containerRef}>
      <Page
        title={data?.name ?? 'Formulier'}
        instanceName={instance?.name}
        spacing="sections"
        back={{ href: PATHS.vacancySetup, text: 'Terug naar Vacatureformulier en taalmodel' }}
      >
        {detail.isPending ? <Loading /> : null}
        {denied ? <EmptyNotice text="Dit is voor beheerders" /> : null}
        {detail.isError && !denied ? <ErrorNotice message={errorMessage(detail.error)} /> : null}

        {data ? (
          <Section title="Bekijk het formulier" level={2}>
            <nldd-container layout="row" gap="16" vertical-alignment="center">
              <FilterSelect
                label="Ingevuld voor"
                value={sampleOf}
                onChange={setPicked}
                width="320px"
                options={[
                  ...(vacancies.data ?? []).map((vacancy) => ({
                    value: vacancy.id,
                    label: `Vacature ${vacancy.function_title}`,
                  })),
                  { value: EXAMPLE, label: 'Voorbeeldwaarden in elk veld' },
                ]}
              />
              <DocumentLink
                href={templateSampleUrl(data.id, sampleOf === EXAMPLE ? undefined : sampleOf)}
                text="Bekijk een ingevuld voorbeeld"
                kind="view"
              />
              <DocumentLink
                href={templateFileUrl(data.id)}
                text="Bekijk het lege formulier"
                kind="view"
              />
            </nldd-container>
          </Section>
        ) : null}

        {data ? (
          <Section title="Wat grip invult" level={2}>
            <nldd-table
              accessible-label="Velden van het formulier en wat grip invult"
              columns="minmax(220px,1fr) minmax(260px,1.4fr)"
            >
              <nldd-table-row slot="header">
                <nldd-text-cell text="Veld in het formulier" />
                <nldd-text-cell text="Grip vult in" />
              </nldd-table-row>
              {data.fields.map((field) => {
                const edit = () => setEditing(field);
                return (
                  <OpenRow key={field.name} onOpen={edit}>
                    <OpenCell
                      text={fieldName(field)}
                      accessibleLabel={`Koppel ${fieldName(field)}`}
                      onOpen={edit}
                      {...(field.label ? { supportingText: field.name } : {})}
                    />
                    {field.state === 'mapped' ? (
                      <nldd-text-cell text={stateText(field)} />
                    ) : (
                      <nldd-cell>
                        <nldd-badge
                          color={field.state === 'missing' ? 'critical' : 'neutral'}
                          text={stateText(field)}
                        />
                      </nldd-cell>
                    )}
                  </OpenRow>
                );
              })}
              <nldd-inline-dialog slot="empty" text="Dit formulier heeft geen velden" />
            </nldd-table>
          </Section>
        ) : null}
      </Page>
      {data ? (
        <FieldSheet
          // A sheet keeps its fields mounted: start again for every field.
          key={editing?.name ?? 'none'}
          detail={data}
          field={editing}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  );
}
