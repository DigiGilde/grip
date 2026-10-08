import { useMutation, useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { ErrorNotice, Quiet, Section } from '@/ui/layout';
import { fetchModelStatus, testModel } from './textWorkApi';
import { Button } from './ui';

/** Which language model drafts texts here, and whether it answers. */
export function ModelStatusSection() {
  const status = useQuery({ queryKey: ['vacancy-texts', 'model'], queryFn: fetchModelStatus });
  const test = useMutation({ mutationFn: testModel });
  if (!status.data) return null;
  return (
    <Section title="Verbinding met het taalmodel">
      <nldd-text>{status.data.provider_text}</nldd-text>
      {status.data.note && <Quiet>{status.data.note}</Quiet>}
      {test.data && (
        <Quiet>
          {test.data.message}
          {test.data.model ? ` ${test.data.model}.` : ''}
        </Quiet>
      )}
      {test.isError && <ErrorNotice message={errorMessage(test.error)} />}
      {status.data.available && (
        <nldd-button-group>
          <Button
            text="Test de verbinding"
            loading={test.isPending}
            onClick={() => test.mutate()}
          />
        </nldd-button-group>
      )}
    </Section>
  );
}
