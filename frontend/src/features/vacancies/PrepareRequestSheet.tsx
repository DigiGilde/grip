import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { assignmentKeys, fetchPersonOptions } from '@/features/assignments/api';
import {
  FRAMEWORK_KEYS,
  fetchFunctionFramework,
  groupChoices,
} from '@/features/function-framework/api';
import { FunctionGroupPicker } from '@/features/function-framework/FunctionGroupPicker';
import { updateVacancy, type ContractType, type Vacancy, type VacancyOptions, type VacancyUpdate } from './api';
import { parseScale, useVacancyChange } from './hooks';
import { budgetLineWarning } from './labels';
import { CheckboxInput, Note, SelectInput, TextInput } from './ui';
import { FormSheet } from '@/ui/layout';

/** Choice in a picker for something that is not in its list. */
const NOT_LISTED = 'none';

interface PrepareRequestSheetProps {
  vacancy: Vacancy;
  options: VacancyOptions | undefined;
  open: boolean;
  onClose: () => void;
}

/**
 * What the request form asks for beyond the role itself: the FGR name with
 * its scale, the type of contract, and who the request is addressed to.
 */
export function PrepareRequestSheet({ vacancy, options, open, onClose }: PrepareRequestSheetProps) {
  const framework = useQuery({
    queryKey: FRAMEWORK_KEYS.current,
    queryFn: () => fetchFunctionFramework(),
    staleTime: 60_000,
    enabled: open,
  });
  const people = useQuery({
    queryKey: assignmentKeys.personOptions,
    queryFn: fetchPersonOptions,
    enabled: open,
  });
  const choices = groupChoices(framework.data);
  const accounts = people.data ?? [];

  const [groupId, setGroupId] = useState(vacancy.function_group_id ?? '');
  // A name that was typed before, or a group that is not in the list.
  const [freeName, setFreeName] = useState(
    vacancy.function_group_id ? '' : (vacancy.fgr_function_name ?? ''),
  );
  const [notListed, setNotListed] = useState(
    !vacancy.function_group_id && Boolean(vacancy.fgr_function_name),
  );
  const [scale, setScale] = useState(
    vacancy.scale === null || vacancy.scale === undefined ? '' : String(vacancy.scale),
  );
  const [deviates, setDeviates] = useState(Boolean(vacancy.scale_deviation_reason));
  const [reason, setReason] = useState(vacancy.scale_deviation_reason ?? '');
  const [contractType, setContractType] = useState<string>(vacancy.contract_type ?? '');
  const [addresseeId, setAddresseeId] = useState(
    vacancy.addressee_name && !vacancy.addressee_has_account ? NOT_LISTED : '',
  );
  const [addressee, setAddressee] = useState(vacancy.addressee_name ?? '');
  const [problem, setProblem] = useState<string | null>(null);
  const change = useVacancyChange(
    vacancy.id,
    (body: VacancyUpdate) => updateVacancy(vacancy.id, body),
    onClose,
  );

  const group = notListed ? undefined : choices.find((choice) => choice.id === groupId);
  const groupScales = group?.scales ?? [];
  const freeScale = !group || deviates;
  const keepsAccount = addresseeId === '' && vacancy.addressee_has_account === true;
  const typedAddressee =
    addresseeId === NOT_LISTED || (!people.isPending && accounts.length === 0);
  const scaleNumber = parseScale(scale);
  const warning = budgetLineWarning(scaleNumber ?? null, vacancy.budget_line_scales);

  function chooseGroup(id: string) {
    setGroupId(id);
    const picked = choices.find((choice) => choice.id === id);
    if (!picked) return;
    setDeviates(false);
    setReason('');
    // One scale is filled in; several narrow the choice.
    if (picked.scales.length === 1) setScale(String(picked.scales[0]));
    else if (!picked.scales.includes(Number(scale))) setScale('');
  }

  function submit() {
    setProblem(null);
    if (scaleNumber === undefined) {
      return setProblem('De schaal is een heel getal van 1 tot en met 19.');
    }
    if (group && scaleNumber !== null && !group.scales.includes(scaleNumber)) {
      if (!deviates || !reason.trim()) {
        return setProblem(
          `Schaal ${scaleNumber} hoort niet bij de functiegroep ${group.name} (${group.scales_text}). Kies een schaal van de groep, of geef aan dat de schaal afwijkt en waarom.`,
        );
      }
    }
    const body: VacancyUpdate = {
      scale: scaleNumber,
      contract_type: (contractType || null) as ContractType | null,
    };
    if (notListed) {
      body.fgr_function_name = freeName.trim() || null;
    } else if (groupId) {
      // By id, so a list that has not loaded yet cannot drop the choice.
      body.function_group_id = groupId;
      body.scale_deviation_reason = deviates ? reason.trim() : null;
    } else {
      body.function_group_id = null;
      body.fgr_function_name = null;
    }
    if (typedAddressee) body.addressee_name = addressee.trim() || null;
    else if (addresseeId !== '') body.addressee_id = addresseeId;
    change.run(body);
  }

  return (
    <FormSheet
      open={open}
      title={`Aanvraag voor ${vacancy.function_title} voorbereiden`}
      submitText="Bewaar"
      onSubmit={submit}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      <Note>
        Dit zijn de gegevens die het aanvraagformulier vraagt. Wat je nog niet weet, laat je
        open; het formulier laat zien wat er nog ontbreekt.
      </Note>
      {!notListed && (
        <FunctionGroupPicker
          label="FGR-functienaam"
          hint="De functiegroep uit het Functiegebouw Rijk. De schalen van de groep bepalen welke schaal je kunt kiezen."
          choices={choices}
          value={groupId}
          onChange={chooseGroup}
          suggestScales={vacancy.budget_line_scales}
          optional
        />
      )}
      <CheckboxInput
        label="De functiegroep staat niet in de lijst"
        checked={notListed}
        onChange={(on) => {
          setNotListed(on);
          if (on) setDeviates(false);
        }}
      />
      {notListed && (
        <TextInput
          label="FGR-functienaam"
          hint="Zoals die op het formulier moet komen. De beheerder kan de lijst aanvullen."
          value={freeName}
          onChange={setFreeName}
          optional
        />
      )}
      {group && group.scales.length === 1 && !deviates && (
        <Note>
          Schaal {group.scales[0]}: de functiegroep {group.name} kent alleen deze schaal.
        </Note>
      )}
      {group && group.scales.length > 1 && !deviates && (
        <SelectInput
          label="Schaal"
          hint={`De functiegroep ${group.name} kent ${group.scales_text}.`}
          value={groupScales.includes(Number(scale)) ? scale : ''}
          onChange={setScale}
          options={groupScales.map((entry) => ({ value: String(entry), label: `Schaal ${entry}` }))}
          placeholder="Nog niet bekend"
          optional
        />
      )}
      {group && (
        <CheckboxInput
          label="De schaal wijkt af van de functiegroep"
          checked={deviates}
          onChange={setDeviates}
        />
      )}
      {freeScale && (
        <TextInput label="Schaal" value={scale} onChange={setScale} keyboard="numeric" optional />
      )}
      {group && deviates && (
        <TextInput
          label="Waarom wijkt de schaal af"
          hint="Komt bij de vacature te staan. Het formulier blijft geldig."
          value={reason}
          onChange={setReason}
          multiline
          required
        />
      )}
      {warning && <nldd-banner variant="warning" size="sm" text={warning} />}
      <SelectInput
        label="Type contract"
        value={contractType}
        onChange={setContractType}
        options={options?.contract_types ?? []}
        placeholder="Nog niet bekend"
        optional
      />
      {accounts.length > 0 && (
        <SelectInput
          label="Aan"
          hint="Wie akkoord moet geven op de aanvraag."
          value={addresseeId}
          onChange={setAddresseeId}
          options={[
            ...accounts.map((person) => ({ value: person.id, label: person.name })),
            { value: NOT_LISTED, label: 'Iemand zonder account' },
          ]}
          placeholder={keepsAccount ? (vacancy.addressee_name ?? 'Kies') : 'Nog niet bekend'}
          optional
        />
      )}
      {typedAddressee && (
        <TextInput
          label={accounts.length > 0 ? 'Naam' : 'Aan'}
          hint={accounts.length > 0 ? undefined : 'Wie akkoord moet geven op de aanvraag.'}
          value={addressee}
          onChange={setAddressee}
          optional
        />
      )}
    </FormSheet>
  );
}
