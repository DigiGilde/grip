import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { PATHS } from '@/paths';
import type { RowAction } from '@/ui/RowActions';
import { assignmentKeys, deleteBudgetLine, type BudgetLine } from '../api';
import { lineName } from './lineText';

/** What a row of a line can do besides opening: its inzet, and going away after a question. */
export function useLineActions(assignmentId: string) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [problem, setProblem] = useState<string | null>(null);
  const remove = useMutation({
    mutationFn: (lineId: string) => deleteBudgetLine(lineId),
    onSuccess: (budget) => {
      queryClient.setQueryData(assignmentKeys.budget(assignmentId), budget);
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
      setProblem(null);
    },
    onError: (error) => setProblem(errorMessage(error)),
  });
  const actionsOf = (line: BudgetLine): RowAction[] => [
    ...(line.kind === 'personnel'
      ? [
          {
            text: 'Bekijk inzet',
            onSelect: () => navigate(`${PATHS.peopleBoard}?opdracht=${assignmentId}`),
          },
        ]
      : []),
    {
      text: 'Verwijder',
      destructive: true,
      confirm: {
        text: `${lineName(line)} verwijderen?`,
        supportingText: line.intended_person_name
          ? `De reservering van ${line.intended_person_name} vervalt ook. Een regel met inzet kan niet weg; haal dan eerst de inzet weg.`
          : 'Een regel met inzet kan niet weg; haal dan eerst de inzet weg.',
        confirmText: 'Verwijder',
      },
      onSelect: () => remove.mutate(line.id),
    },
  ];
  return { actionsOf, problem };
}
