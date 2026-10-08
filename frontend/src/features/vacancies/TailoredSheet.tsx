/**
 * Asking for a draft of the vacancy text that fits this vacancy. Used where
 * a text is started: the Tekst tab and the page the text is written on.
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { FormSheet, Quiet } from '@/ui/layout';
import { VACANCY_KEYS } from './api';
import { TEXT_WORK_KEY, draftTailored, type VacancyTextWork } from './textWorkApi';
import { TextInput } from './ui';

interface TailoredSheetProps {
  vacancyId: string;
  note: string | null | undefined;
  onClose: () => void;
  /** After the draft is there, with the text work as it now is. */
  onDrafted?: (work: VacancyTextWork) => void;
}

export function TailoredSheet({ vacancyId, note, onClose, onDrafted }: TailoredSheetProps) {
  const [instruction, setInstruction] = useState('');
  const queryClient = useQueryClient();
  const draft = useMutation({
    mutationFn: () => draftTailored(vacancyId, instruction),
    onSuccess: (work) => {
      queryClient.setQueryData(TEXT_WORK_KEY(vacancyId), work);
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.detail(vacancyId) });
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
      onDrafted?.(work);
      onClose();
    },
  });
  return (
    <FormSheet
      open
      title="Stel een tekst op maat op"
      submitText={draft.isPending ? 'Het concept wordt geschreven' : 'Stel een concept op'}
      onSubmit={() => draft.mutate()}
      onClose={onClose}
      busy={draft.isPending}
      error={draft.isError ? errorMessage(draft.error) : null}
    >
      <TextInput
        label="Wat is bijzonder aan deze vacature"
        hint="Bijvoorbeeld wat het team maakt en waar de nadruk op ligt. Noem geen personen."
        value={instruction}
        onChange={setInstruction}
        multiline
        optional
      />
      <Quiet>
        {draft.isPending
          ? 'Dit duurt ongeveer een halve minuut.'
          : 'Het concept volgt de standaardtekst van de rol. Je leest het, past het aan en stelt het vast.'}
        {note ? ` ${note}` : ''}
      </Quiet>
    </FormSheet>
  );
}
