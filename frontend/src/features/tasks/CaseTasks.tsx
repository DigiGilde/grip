import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { RouterLinks } from '@/layout/RouterLinks';
import { ActionBar } from '@/ui/ActionBar';
import { EmptyNotice, Facts, FormSheet, LoadError, Loading, Section, Stack } from '@/ui/layout';
import { DateInput, SelectInput, TextInput } from '@/features/vacancies/ui';
import {
  TASK_KEYS,
  createTask,
  fetchCaseTasks,
  type CaseKind,
  type CaseTasks as CaseTasksData,
  type Track,
} from './api';
import { useOpenTask } from './moves';
import { TaskSheet, TaskTable } from './parts';

/** Where each track of a case stands, one quiet line per track. */
export function TrackStandings({ tracks }: { tracks: readonly Track[] }) {
  return (
    <Facts
      label="Stand per spoor"
      labelWidth="160px"
      facts={tracks.map((track) => ({ label: track.label, value: track.standing }))}
    />
  );
}

interface NewTaskSheetProps {
  data: CaseTasksData;
  open: boolean;
  onClose: () => void;
}

function NewTaskSheet({ data, open, onClose }: NewTaskSheetProps) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [track, setTrack] = useState(data.tracks[0]?.key ?? '');
  const [dueOn, setDueOn] = useState('');
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () =>
      createTask({
        case_kind: data.case_kind,
        case_id: data.case_id,
        title: title.trim(),
        ...(track ? { track } : {}),
        ...(dueOn ? { due_on: dueOn } : {}),
      }),
    onSuccess: () => {
      setTitle('');
      setDueOn('');
      setError(null);
      void queryClient.invalidateQueries({ queryKey: TASK_KEYS.all });
      onClose();
    },
    onError: (failure) => setError(errorMessage(failure)),
  });
  return (
    <FormSheet
      open={open}
      title="Nieuwe taak"
      submitText="Voeg taak toe"
      onSubmit={() => {
        if (title.trim() === '') setError('Geef de taak een naam.');
        else save.mutate();
      }}
      onClose={onClose}
      busy={save.isPending}
      error={error}
    >
      <TextInput label="Wat moet er gebeuren" value={title} onChange={setTitle} required />
      {data.tracks.length > 1 && (
        <SelectInput
          label="Spoor"
          value={track}
          onChange={setTrack}
          options={data.tracks.map((item) => ({ value: item.key, label: item.label }))}
        />
      )}
      <DateInput label="Vóór" value={dueOn} onChange={setDueOn} optional />
    </FormSheet>
  );
}

/**
 * The work on one case: where each track stands, and the tasks per track.
 * Tasks of the plan arise and close by themselves; a task of your own can
 * be added here.
 */
export function CaseTasks({ kind, caseId }: { kind: CaseKind; caseId: string }) {
  const [adding, setAdding] = useState(false);
  const [openId, openTask] = useOpenTask();
  const query = useQuery({
    queryKey: TASK_KEYS.ofCase(kind, caseId),
    queryFn: () => fetchCaseTasks(kind, caseId),
    enabled: caseId !== '',
  });
  const data = query.data;
  const withTasks = data?.tracks.filter((track) => track.tasks.length > 0) ?? [];
  return (
    <nldd-simple-section>
      <RouterLinks>
        <Stack gap="section">
          <Stack gap="group">
            {data?.can_add && (
              <ActionBar
                label="Acties voor de taken"
                filters={[]}
                actions={[{ text: 'Nieuwe taak', onClick: () => setAdding(true) }]}
              />
            )}
            {query.isPending && <Loading />}
            {query.isError && <LoadError error={query.error} retry={() => void query.refetch()} />}
            {data && withTasks.length === 0 && <EmptyNotice text="Geen taken" />}
          </Stack>
          {withTasks.map((track) => (
            <Section key={track.key} title={track.label}>
              <TaskTable
                label={`Taken in het spoor ${track.label}`}
                tasks={track.tasks}
                withCase={false}
                onOpen={openTask}
              />
            </Section>
          ))}
        </Stack>
      </RouterLinks>
      {data?.can_add && <NewTaskSheet data={data} open={adding} onClose={() => setAdding(false)} />}
      <TaskSheet taskId={openId} onClose={() => openTask(null)} />
    </nldd-simple-section>
  );
}

/** The tab "Taken" of an assignment. */
export function AssignmentTasksTab() {
  const { assignmentId = '' } = useParams();
  return <CaseTasks kind="assignment" caseId={assignmentId} />;
}

/** The tab "Taken" of a vacancy. */
export function VacancyTasksTab() {
  const { vacancyId = '' } = useParams();
  return <CaseTasks kind="vacancy" caseId={vacancyId} />;
}
