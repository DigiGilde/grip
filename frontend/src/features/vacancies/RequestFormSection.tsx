import { DocumentLink } from '@/ui/Icon';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatDate } from '@/lib/format';
import { ErrorNotice, FormSheet, LoadError, Quiet, Stack } from '@/ui/layout';
import {
  changedText,
  fetchRequestForms,
  keptFormUrl,
  makeRequestForm,
  recordSignedForm,
  requestFormsKey,
  type KeptForm,
  type RequestForms,
} from './requestForms';
import { Button, FileInput } from './ui';

function madeLine(form: KeptForm): string {
  return [
    `gemaakt op ${formatDate(form.made_at)}`,
    form.made_by_name ? `door ${form.made_by_name}` : null,
  ]
    .filter(Boolean)
    .join(' ');
}

function FormRow({ vacancyId, form, text }: { vacancyId: string; form: KeptForm; text: string }) {
  return (
    <nldd-list-item>
      <nldd-cell width="full">
        <nldd-container gap="4">
          <DocumentLink href={keptFormUrl(vacancyId, form.id)} text={text} kind="view" />
          <nldd-text color="secondary" size="sm">
            {madeLine(form)}
          </nldd-text>
        </nldd-container>
      </nldd-cell>
    </nldd-list-item>
  );
}

/**
 * The request form of a vacancy: made once and kept, with the earlier
 * versions and the signed copy. Shows nothing while the instance has no
 * blank form in use.
 */
export function RequestFormSection({ vacancyId }: { vacancyId: string }) {
  const queryClient = useQueryClient();
  const forms = useQuery({
    queryKey: requestFormsKey(vacancyId),
    queryFn: () => fetchRequestForms(vacancyId),
  });
  const [recording, setRecording] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const done = (saved: RequestForms) => {
    queryClient.setQueryData(requestFormsKey(vacancyId), saved);
    setRecording(false);
    setFile(null);
  };
  const make = useMutation({ mutationFn: () => makeRequestForm(vacancyId), onSuccess: done });
  const record = useMutation({
    mutationFn: (chosen: File) => recordSignedForm(vacancyId, chosen),
    onSuccess: done,
    onError: (failure) => setError(errorMessage(failure)),
  });

  if (forms.isError) return <LoadError error={forms.error} retry={() => void forms.refetch()} />;
  const data = forms.data;
  if (!data || !data.available) return null;
  const { current, earlier, signed, changed } = data;
  const outOfDate = current !== null && changed.length > 0;
  // The form prints these; without them it would go out with empty boxes.
  const missing = data.missing ?? [];

  return (
    <Stack gap="group">
      {make.isError ? <ErrorNotice message={errorMessage(make.error)} /> : null}
      {outOfDate ? (
        <nldd-banner
          variant="warning"
          size="sm"
          text="Het aanvraagformulier loopt achter op de vacature"
          supporting-text={`Veranderd sinds het is gemaakt: ${changedText(changed)}.`}
        />
      ) : null}
      {current || signed.length > 0 ? (
        <nldd-list appearance="box-base" accessible-label="Aanvraagformulieren van deze vacature">
          {signed.map((form) => (
            <FormRow
              key={form.id}
              vacancyId={vacancyId}
              form={form}
              text="Bekijk het getekende formulier"
            />
          ))}
          {current ? (
            <FormRow vacancyId={vacancyId} form={current} text="Bekijk het aanvraagformulier" />
          ) : null}
          {earlier.map((form, index) => (
            <FormRow
              key={form.id}
              vacancyId={vacancyId}
              form={form}
              text={`Eerdere versie ${earlier.length - index}`}
            />
          ))}
        </nldd-list>
      ) : null}
      {data.may_make && missing.length > 0 ? (
        <Quiet>
          Het aanvraagformulier kun je maken zodra de aanvraag compleet is. Ontbreekt nog:{' '}
          {missing.join(', ')}.
        </Quiet>
      ) : null}
      {data.may_make && (missing.length === 0 || current) ? (
        <nldd-button-group>
          {missing.length === 0 && (current === null || outOfDate) ? (
            <Button
              text={current === null ? 'Maak aanvraagformulier' : 'Maak opnieuw'}
              appearance="secondary"
              loading={make.isPending}
              onClick={() => make.mutate()}
            />
          ) : null}
          {current ? (
            <Button
              text="Leg het getekende formulier vast"
              onClick={() => {
                setError(null);
                setRecording(true);
              }}
            />
          ) : null}
        </nldd-button-group>
      ) : null}
      {/* Only right after making it, when it says what to do next. */}
      {make.isSuccess && current && !outOfDate ? (
        <Quiet>Stuur het formulier naar de adviseur; die vult het buiten grip aan.</Quiet>
      ) : null}
      <FormSheet
        open={recording}
        title="Getekend formulier vastleggen"
        submitText="Leg vast"
        busy={record.isPending}
        error={error}
        onClose={() => setRecording(false)}
        onSubmit={() => {
          if (!file) {
            setError('Kies het getekende formulier als pdf.');
            return;
          }
          record.mutate(file);
        }}
      >
        <FileInput label="Getekend formulier" accept="application/pdf" onChange={setFile} />
      </FormSheet>
    </Stack>
  );
}
