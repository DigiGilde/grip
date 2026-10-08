import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import {
  Button,
  DateInput,
  EmptyNotice,
  ErrorNotice,
  Loading,
  SectionHeading,
  SelectInput,
  TextInput,
} from '@/features/assignments/ui';
import { NodePicker } from '@/features/nodes';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import { clientKeys, fetchClientOptions, requestQuote } from './api';
import { clientAssignmentPath } from './paths';
import { validateRequest } from './requestForm';
import './register';

/**
 * Ask a contractor for a quote. The request becomes an assignment in this
 * instance, with this organisation as client; the contractor receives it in
 * its own instance and answers with a quote.
 */
export function RequestQuotePage() {
  const instance = useInstance();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const options = useQuery({ queryKey: clientKeys.options(), queryFn: fetchClientOptions });

  const [contractor, setContractor] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [context, setContext] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: requestQuote,
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: clientKeys.all });
      navigate(clientAssignmentPath(created.id));
    },
    onError: (failure) => setError(errorMessage(failure)),
  });

  const contractors = options.data?.contractors ?? [];
  const chosen = contractors.find((item) => item.peer_id === contractor);

  const submit = () => {
    const problem = validateRequest({ contractor, name, startDate, endDate });
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    send.mutate({
      contractor_peer_id: contractor,
      name: name.trim(),
      description: description.trim() || null,
      start_date: startDate || null,
      end_date: endDate || null,
      context_uris: context,
    });
  };

  return (
    <>
      <nldd-simple-section>
        <PageHeading text="Offerte aanvragen" instanceName={instance?.name} />
        {options.isPending ? <Loading /> : null}
        {options.isError ? <ErrorNotice message={errorMessage(options.error)} /> : null}
        {options.data && !options.data.may_request ? (
          <EmptyNotice
            text="Je kunt geen offerte aanvragen"
            supportingText="Een offerte aanvragen kan met de functie aanvrager. De beheerder van deze instantie kent functies toe."
          />
        ) : null}
        {options.data?.may_request ? (
          <nldd-container gap="16">
            <nldd-text>
              Je vraagt een opdrachtnemer om een offerte. De opdrachtnemer ontvangt de aanvraag
              in zijn eigen instantie en stuurt een offerte terug, die een tekenbevoegde van deze
              organisatie kan accepteren.
            </nldd-text>
            {options.data.problem ? (
              <nldd-banner variant="warning" size="sm" text={options.data.problem} />
            ) : null}
            <SelectInput
              label="Opdrachtnemer"
              value={contractor}
              onChange={setContractor}
              placeholder="Kies een opdrachtnemer"
              required
              options={contractors.map((item) => ({ value: item.peer_id, label: item.name }))}
              hint="Organisaties waarmee deze instantie is gekoppeld."
            />
            {chosen && !chosen.reachable ? (
              <nldd-banner
                variant="warning"
                size="sm"
                text="Met deze opdrachtnemer is het contract nog niet compleet vastgelegd"
                supporting-text="De aanvraag wordt vastgelegd, maar kan pas worden verstuurd als de beheerder de koppeling heeft aangevuld."
              />
            ) : null}
            <TextInput
              label="Naam van de aanvraag"
              value={name}
              onChange={setName}
              required
              hint="Zo heet de opdracht straks bij beide organisaties."
            />
            <TextInput
              label="Wat vraag je"
              value={description}
              onChange={setDescription}
              optional
              multiline
              hint="Beschrijf het gewenste resultaat. Zet hier geen namen van personen in."
            />
            <DateInput
              label="Gewenste begindatum"
              value={startDate}
              onChange={setStartDate}
              optional
            />
            <DateInput label="Gewenste einddatum" value={endDate} onChange={setEndDate} optional />
          </nldd-container>
        ) : null}
      </nldd-simple-section>

      {options.data?.may_request ? (
        <>
          <nldd-simple-section>
            <SectionHeading text="Context" />
            <NodePicker value={context} onChange={setContext} />
          </nldd-simple-section>
          <nldd-simple-section>
            {error ? <nldd-banner variant="critical" size="sm" text={error} /> : null}
            <nldd-button-group>
              <Button
                text="Verstuur aanvraag"
                appearance="primary"
                loading={send.isPending}
                onClick={submit}
              />
              <Button text="Annuleer" onClick={() => navigate(PATHS.client)} />
            </nldd-button-group>
          </nldd-simple-section>
        </>
      ) : null}
    </>
  );
}
