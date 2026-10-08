import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, errorMessage } from '@/api/client';
import { centsToInput, parseEuroToCents } from '@/features/assignments/money';
import { Button, SelectInput, TextInput } from '@/features/assignments/ui';
import { useInstance } from '@/layout/useInstance';
import { formatEuro } from '@/lib/format';
import {
  EmptyNotice,
  ErrorNotice,
  Facts,
  FormSheet,
  Loading,
  Page,
  Quiet,
  Section,
} from '@/ui/layout';
import {
  APPROVAL_MODE_LABELS,
  APPROVER_RIGHT,
  SETTING_ALLOW_SELF,
  SETTING_MODE,
  SETTING_REFERENCE_PREFIX,
  SETTING_THRESHOLD,
  approvalKeys,
  fetchInstanceSettings,
  saveInstanceSettings,
  type InstanceSetting,
} from './approval';
import { CheckboxInput } from './ui';

function valueOf(items: readonly InstanceSetting[], key: string): unknown {
  return items.find((item) => item.key === key)?.value;
}

/** When the organisation approves a quote internally before offering it. */
function whenText(mode: string, thresholdCents: number): string {
  if (mode === 'from_amount') return `Vanaf ${formatEuro(thresholdCents)}`;
  return APPROVAL_MODE_LABELS[mode] ?? mode;
}

/** How this organisation handles its quotes. For the beheerder. */
export function QuoteSettingsPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: approvalKeys.settings,
    queryFn: fetchInstanceSettings,
    retry: false,
  });
  const items = query.data?.items ?? [];
  const mode = String(valueOf(items, SETTING_MODE) ?? 'never');
  const threshold = Number(valueOf(items, SETTING_THRESHOLD) ?? 0);
  const allowSelf = Boolean(valueOf(items, SETTING_ALLOW_SELF));

  const prefixSetting = items.find((item) => item.key === SETTING_REFERENCE_PREFIX);
  const prefix = String(prefixSetting?.value || prefixSetting?.default || '');
  const year = new Date().getFullYear();
  const [prefixOpen, setPrefixOpen] = useState(false);
  const [nextPrefix, setNextPrefix] = useState('');

  const [open, setOpen] = useState(false);
  const [nextMode, setNextMode] = useState('never');
  const [nextThreshold, setNextThreshold] = useState('');
  const [nextAllowSelf, setNextAllowSelf] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: saveInstanceSettings,
    onSuccess: async (saved) => {
      queryClient.setQueryData(approvalKeys.settings, saved);
      setOpen(false);
      setPrefixOpen(false);
      await queryClient.invalidateQueries({ queryKey: ['quotes'] });
    },
    onError: (failure) => setError(errorMessage(failure)),
  });

  const edit = () => {
    setNextMode(mode);
    setNextThreshold(threshold > 0 ? centsToInput(threshold) : '');
    setNextAllowSelf(allowSelf);
    setError(null);
    setOpen(true);
  };
  const forbidden = query.error instanceof ApiError && query.error.status === 403;

  return (
    <>
      <Page title="Offertes" instanceName={instance?.name} spacing="sections">
        {query.isPending ? <Loading /> : null}
        {query.isError && forbidden ? <EmptyNotice text="Beheer is voor beheerders" /> : null}
        {query.isError && !forbidden ? <ErrorNotice message={errorMessage(query.error)} /> : null}
        {query.data ? (
          <Section title="Interne goedkeuring" level={2}>
            <Facts
              label="Instellingen voor interne goedkeuring"
              facts={[
                {
                  label: 'Goedkeuring nodig',
                  value: whenText(mode, threshold),
                },
                ...(mode === 'never'
                  ? []
                  : [
                      {
                        label: 'Eigen offerte goedkeuren',
                        value: allowSelf ? 'Mag' : 'Mag niet: een ander keurt goed',
                      },
                    ]),
              ]}
            />
            {mode === 'never' ? null : (
              <Quiet>
                Goedkeuren kan wie het recht "{APPROVER_RIGHT}" heeft. Je kent het toe bij Team,
                onder Rechten in grip van een persoon.
              </Quiet>
            )}
            <nldd-button-group>
              <Button text="Wijzig" onClick={edit} />
            </nldd-button-group>
          </Section>
        ) : null}
        {query.data && prefixSetting ? (
          <Section title="Kenmerk" level={2}>
            <Facts
              label="Het kenmerk van een offerte"
              facts={[
                { label: 'Voorvoegsel', value: prefix },
                {
                  label: 'Volgende offerte heet bijvoorbeeld',
                  value: `${prefix}-${year}-0001`,
                },
              ]}
            />
            <nldd-button-group>
              <Button
                text="Wijzig voorvoegsel"
                onClick={() => {
                  setNextPrefix(String(prefixSetting.value ?? ''));
                  setError(null);
                  setPrefixOpen(true);
                }}
              />
            </nldd-button-group>
          </Section>
        ) : null}
      </Page>

      <FormSheet
        open={prefixOpen}
        title="Voorvoegsel van het kenmerk wijzigen"
        submitText="Bewaar"
        busy={save.isPending}
        error={prefixOpen ? error : null}
        onClose={() => setPrefixOpen(false)}
        onSubmit={() => {
          const value = nextPrefix.trim().toUpperCase();
          if (!/^[A-Z0-9]{0,10}$/.test(value)) {
            setError('Gebruik hooguit 10 letters en cijfers, zonder spaties.');
            return;
          }
          setError(null);
          save.mutate({ [SETTING_REFERENCE_PREFIX]: value });
        }}
      >
        <nldd-text>
          Geldt voor offertes die je hierna maakt. Het kenmerk van een bestaande offerte verandert
          niet, en de nummering loopt door.
        </nldd-text>
        <TextInput
          label="Voorvoegsel"
          hint={`Leeg laten geeft ${String(prefixSetting?.default ?? '')}`}
          value={nextPrefix}
          onChange={setNextPrefix}
          optional
        />
      </FormSheet>

      <FormSheet
        open={open}
        title="Interne goedkeuring wijzigen"
        submitText="Bewaar"
        busy={save.isPending}
        error={open ? error : null}
        onClose={() => setOpen(false)}
        onSubmit={() => {
          const values: Record<string, unknown> = {
            [SETTING_MODE]: nextMode,
            [SETTING_ALLOW_SELF]: nextAllowSelf,
          };
          if (nextMode === 'from_amount') {
            const cents = parseEuroToCents(nextThreshold);
            if (cents === null || cents <= 0) {
              setError('Vul het bedrag in vanaf waar goedkeuring nodig is.');
              return;
            }
            values[SETTING_THRESHOLD] = cents;
          }
          setError(null);
          save.mutate(values);
        }}
      >
        <SelectInput
          label="Een offerte intern goedkeuren voor ze wordt aangeboden"
          value={nextMode}
          onChange={setNextMode}
          options={Object.entries(APPROVAL_MODE_LABELS).map(([value, label]) => ({ value, label }))}
          required
        />
        {nextMode === 'from_amount' ? (
          <TextInput
            label="Vanaf welk offertebedrag"
            hint="In euro's"
            value={nextThreshold}
            onChange={setNextThreshold}
            required
          />
        ) : null}
        {nextMode === 'never' ? null : (
          <CheckboxInput
            label="Wie de goedkeuring vraagt mag de eigen offerte ook goedkeuren"
            checked={nextAllowSelf}
            onChange={setNextAllowSelf}
          />
        )}
      </FormSheet>
    </>
  );
}
