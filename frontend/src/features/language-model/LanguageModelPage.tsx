import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError, errorMessage } from '@/api/client';
import { SETUP_KEYS, fetchLanguageModel } from '@/features/form-templates/api';
import { fetchModelStatus, testModel } from '@/features/vacancies/textWorkApi';
import { RouterLinks } from '@/layout/RouterLinks';
import { useAdminBack } from '@/layout/useAdminBack';
import { useInstance } from '@/layout/useInstance';
import { Button } from '@/ui/Button';
import {
  ErrorNotice,
  type Fact,
  Facts,
  LoadError,
  Loading,
  NoAccess,
  Page,
  Quiet,
  Section,
} from '@/ui/layout';

const USED_FOR =
  'Een vacaturetekst, een onderdeel van een offerte en een voorstel bij een open plek';

/**
 * The language model as a connection: which one drafts texts here, whether
 * it answers, what goes to it and how often it may be asked. The settings
 * come from the environment, so they are shown and not edited.
 */
export function LanguageModelPage() {
  const instance = useInstance();
  const adminBack = useAdminBack();
  const status = useQuery({
    queryKey: ['vacancy-texts', 'model'],
    queryFn: fetchModelStatus,
    retry: false,
  });
  const model = useQuery({
    queryKey: [...SETUP_KEYS.model, false],
    queryFn: () => fetchLanguageModel(false),
    retry: false,
  });
  const test = useMutation({ mutationFn: testModel });
  const denied = status.error instanceof ApiError && status.error.status === 403;
  const data = status.data;
  // What is missing matters only while no model answers here.
  const missing = data && !data.available ? (model.data?.missing_settings ?? []) : [];
  const facts: Fact[] = data
    ? [
        { label: 'Model', value: data.provider_text },
        ...(model.data?.model_id
          ? [{ label: 'Naam van het model', value: model.data.model_id }]
          : []),
        ...(data.available
          ? [
              { label: 'Gebruikt voor', value: USED_FOR },
              {
                label: 'Per persoon',
                value: `${data.calls_per_person_per_hour} verzoeken per uur`,
              },
              {
                label: 'Voor iedereen samen',
                value: `${data.calls_per_instance_per_hour} verzoeken per uur`,
              },
            ]
          : []),
      ]
    : [];

  return (
    <RouterLinks>
      <Page title="Taalmodel" instanceName={instance?.name} spacing="sections" back={adminBack}>
        {denied ? (
          <NoAccess who="Beheer is voor beheerders. Wie dat zijn zie je onder Team." />
        ) : (
          <>
            <Section title="Verbinding">
              {status.isPending && <Loading />}
              {status.isError && (
                <LoadError error={status.error} retry={() => void status.refetch()} />
              )}
              {data && !data.available && (
                <nldd-text>
                  Er is geen taalmodel verbonden. Teksten schrijf je zelf, met de standaardteksten
                  als begin.
                </nldd-text>
              )}
              {data?.note && <Quiet>{data.note}</Quiet>}
              {missing.length > 0 && <Quiet>Ontbreekt in de omgeving: {missing.join(', ')}</Quiet>}
              {facts.length > 0 && <Facts label="Het taalmodel" facts={facts} />}
              {test.data && (
                <Quiet>
                  {test.data.message}
                  {test.data.model ? ` ${test.data.model}.` : ''}
                </Quiet>
              )}
              {test.isError && <ErrorNotice message={errorMessage(test.error)} />}
              {data?.available && (
                <nldd-button-group>
                  <Button
                    text="Test de verbinding"
                    loading={test.isPending}
                    onClick={() => test.mutate()}
                  />
                </nldd-button-group>
              )}
            </Section>
            {data?.available && (
              <Section title="Wat ernaartoe gaat">
                <nldd-text>
                  Naar het model gaan de gegevens van de vacature of de opdracht, de standaardtekst
                  als voorbeeld, wat de organisatie over zichzelf zegt in de standaardteksten, en de
                  beleidscontext van de opdracht.
                </nldd-text>
                <nldd-text>
                  Namen van collega’s en kandidaten, tarieven van personen en kostprijzen gaan er
                  niet naartoe. Wat het model schrijft is een voorstel; een mens stelt de tekst
                  vast.
                </nldd-text>
              </Section>
            )}
          </>
        )}
      </Page>
    </RouterLinks>
  );
}
