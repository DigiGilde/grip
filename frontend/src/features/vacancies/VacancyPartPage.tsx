import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { NoAccess, Page, type PageKind } from '@/ui/layout';
import { PrimaryTakenContext } from '@/ui/primary';
import { vacancyPartPath, type VacancyPartKey } from './paths';
import { useVacancyShell, type VacancyStep } from './shell';
import { Button } from './ui';

const TASKS_TITLE = 'Alle taken van deze vacature';

/** What a reader hears at the address of a part they do not have. */
export const NOT_FOR_THIS_READER = 'Dit onderdeel is er voor jou niet, of nu nog niet.';

/** The primary button of a page of the vacancy: the reader's one next step. */
export function StepButton({ step }: { step: VacancyStep }) {
  const { openSheet } = useVacancyShell();
  const navigate = useNavigate();
  return (
    <Button
      text={step.text}
      appearance="primary"
      onClick={() => (step.sheet ? openSheet(step.sheet) : navigate(step.href))}
    />
  );
}

interface VacancyPartPageProps {
  part: Exclude<VacancyPartKey, 'landing'>;
  kind: PageKind;
  spacing?: 'blocks' | 'sections';
  /** The part's own main action, in the head, when the next step does not stand there. */
  action?: ReactNode;
  children: ReactNode;
}

/**
 * One part of a vacancy as a page of its own: back to the vacancy, the name
 * of the part with the next step when it is done here, and on a wide screen
 * the bar to the other parts. The server decides which parts the reader has.
 */
export function VacancyPartPage({ part, kind, spacing, action, children }: VacancyPartPageProps) {
  const { vacancy, parts, tasksLink, step, instanceName } = useVacancyShell();
  const back = {
    href: vacancyPartPath(vacancy.id, 'landing'),
    text: `Terug naar ${vacancy.function_title}`,
  };
  const title = part === 'tasks' ? tasksLink && TASKS_TITLE : parts.find((row) => row.key === part)?.label;
  if (!title) {
    return (
      <Page kind="document" title={vacancy.function_title} instanceName={instanceName} back={back}>
        <NoAccess who={NOT_FOR_THIS_READER} />
      </Page>
    );
  }
  return (
    <Page
      kind={kind}
      spacing={spacing}
      title={title}
      tabName={`${title}, ${vacancy.function_title}`}
      instanceName={instanceName}
      back={back}
      action={step ? <StepButton step={step} /> : action}
      tabs={{
        label: `Onderdelen van de vacature ${vacancy.function_title}`,
        current: part,
        narrow: 'hide',
        items: parts.map((row) => ({
          key: row.key,
          text: row.label,
          href: vacancyPartPath(vacancy.id, row.key),
        })),
      }}
    >
      <PrimaryTakenContext.Provider value={step !== null}>{children}</PrimaryTakenContext.Provider>
    </Page>
  );
}
