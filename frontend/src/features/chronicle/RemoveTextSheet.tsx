import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { errorMessage } from '@/api/client';
import { assignmentKeys } from '@/features/assignments/api';
import { CheckboxField } from '@/features/team/ui/controls';
import { FormSheet, Quiet } from '@/ui/layout';
import { chronicleKeys, restateMoment, type RemovableText } from './api';

const NOTHING_CHOSEN = 'Kies de tekst die je wilt verwijderen.';

interface RemoveTextSheetProps {
  assignmentId: string;
  seq: number;
  texts: readonly RemovableText[];
  open: boolean;
  onClose: () => void;
}

/** Taking a typed text out of one moment: the moment is erased and recorded again without it. */
export function RemoveTextSheet({ assignmentId, seq, texts, open, onClose }: RemoveTextSheetProps) {
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const [problem, setProblem] = useState<string | null>(null);
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setChosen(new Set());
      setProblem(null);
    }
  }
  const restate = useMutation({
    mutationFn: (columns: string[]) => restateMoment(assignmentId, seq, columns),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: chronicleKeys.moments(assignmentId) }),
        queryClient.invalidateQueries({ queryKey: assignmentKeys.all }),
      ]);
      onClose();
    },
    onError: (error) => setProblem(errorMessage(error)),
  });
  const toggle = (key: string, checked: boolean) =>
    setChosen((current) => {
      const next = new Set(current);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
  const submit = () => {
    const columns = texts.filter((text) => chosen.has(text.key)).map((text) => text.key);
    if (columns.length === 0) {
      setProblem(NOTHING_CHOSEN);
      return;
    }
    setProblem(null);
    restate.mutate(columns);
  };
  return (
    <FormSheet
      open={open}
      title="Tekst verwijderen uit dit moment"
      submitText="Verwijder tekst"
      onSubmit={submit}
      onClose={onClose}
      busy={restate.isPending}
      error={problem}
    >
      <Quiet>
        Grip wist dit moment en legt het opnieuw vast zonder de gekozen tekst. Andere vastleggingen
        van deze opdracht met dezelfde tekst worden ook gewist. Wat al naar een andere organisatie
        is gestuurd, haalt dit niet terug.
      </Quiet>
      {texts.map((text) => (
        <nldd-form-field
          key={text.key}
          label={text.label}
          {...(text.kept.length > 0 ? { 'supporting-label': text.kept.join(' ') } : {})}
        >
          <CheckboxField
            label={text.text ?? text.label}
            checked={chosen.has(text.key)}
            onChange={(checked) => toggle(text.key, checked)}
          />
        </nldd-form-field>
      ))}
    </FormSheet>
  );
}
