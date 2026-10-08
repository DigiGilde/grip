import { useState } from 'react';
import { fillVacancy, withdrawVacancy, type Vacancy } from './api';
import { useVacancyChange } from './hooks';
import { Button, FormSheet, Note, SectionHeading, TextInput } from './ui';

type Closing = 'fill' | 'withdraw';

const TEXTS: Record<Closing, { title: string; submit: string; note: string; hint: string }> = {
  fill: {
    title: 'Vacature als vervuld melden',
    submit: 'Meld als vervuld',
    note: 'De vacature verdwijnt uit de open rollen. Dit is niet terug te draaien. Wie de rol vervult leg je vast als inzet op de begrotingsregel.',
    hint: 'Bijvoorbeeld per wanneer de rol is ingevuld.',
  },
  withdraw: {
    title: 'Vacature intrekken',
    submit: 'Trek in',
    note: 'De vacature verdwijnt uit de open rollen en wordt niet vervuld. Dit is niet terug te draaien.',
    hint: 'Waarom de vacature vervalt.',
  },
};

/** The two ways a vacancy ends: filled, or withdrawn. */
export function ClosingSection({ vacancy }: { vacancy: Vacancy }) {
  const [closing, setClosing] = useState<Closing>('fill');
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const change = useVacancyChange(
    vacancy.id,
    (input: { closing: Closing; note: string }) =>
      input.closing === 'fill'
        ? fillVacancy(vacancy.id, input.note || undefined)
        : withdrawVacancy(vacancy.id, input.note || undefined),
    () => setOpen(false),
  );
  const { can_fill: canFill, can_withdraw: canWithdraw } = vacancy.permissions;
  if (!canFill && !canWithdraw) return null;

  function show(next: Closing) {
    setClosing(next);
    setNote('');
    change.reset();
    setOpen(true);
  }

  const texts = TEXTS[closing];
  return (
    <>
      <SectionHeading text="Afronden" />
      <nldd-button-group>
        {canFill && <Button text="Meld als vervuld" onClick={() => show('fill')} />}
        {canWithdraw && (
          <Button text="Trek in" appearance="neutral-transparent" onClick={() => show('withdraw')} />
        )}
      </nldd-button-group>
      <FormSheet
        open={open}
        title={texts.title}
        submitText={texts.submit}
        onSubmit={() => change.run({ closing, note: note.trim() })}
        onClose={() => setOpen(false)}
        busy={change.busy}
        error={change.error}
      >
        <Note>{texts.note}</Note>
        <TextInput
          label="Toelichting"
          hint={texts.hint}
          value={note}
          onChange={setNote}
          multiline
          optional
        />
      </FormSheet>
    </>
  );
}
