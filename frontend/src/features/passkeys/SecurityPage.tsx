import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { TextInput } from '@/features/assignments/ui';
import { Button } from '@/features/team/ui/controls';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import { ROW_ACTIONS_COLUMN, RowActions, RowActionsHeader } from '@/ui/RowActions';
import {
  EmptyNotice,
  ErrorNotice,
  FormFields,
  FormSheet,
  LoadError,
  Loading,
  Page,
  Quiet,
  Stack,
} from '@/ui/layout';
import {
  PASSKEYS_KEY,
  fetchPasskeys,
  isCancellation,
  passkeysSupported,
  registerPasskey,
  revokePasskey,
  type Passkey,
  type PasskeyList,
} from './api';

function usedText(passkey: Passkey): string {
  return passkey.last_used_at
    ? `Laatst gebruikt op ${formatDate(passkey.last_used_at)}`
    : 'Nog niet gebruikt';
}

/** What a passkey is for here, in the words of what the person does with it. */
function purpose(list: PasskeyList): string {
  const confirm =
    'Met een passkey bevestig je een akkoord of een goedkeuring op je eigen apparaat.';
  if (!list.login_enabled) return confirm;
  return `${confirm} Je logt er ook mee in, tot ${list.login_max_age_days} dagen na je laatste login met SSO Rijk.`;
}

/** A person's own passkeys: which there are, making one, withdrawing one. */
export function SecurityPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: PASSKEYS_KEY, queryFn: fetchPasskeys, retry: false });
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: PASSKEYS_KEY });

  const register = useMutation({
    mutationFn: () => registerPasskey(label.trim() || 'Passkey'),
    onSuccess: async () => {
      setOpen(false);
      await refresh();
    },
    onError: (failure) =>
      setError(
        isCancellation(failure)
          ? 'Het vastleggen is afgebroken. Er is niets vastgelegd.'
          : errorMessage(failure),
      ),
  });

  const revoke = useMutation({
    mutationFn: revokePasskey,
    onSuccess: refresh,
    onError: (failure) => setRowError(errorMessage(failure)),
  });

  const list = query.data;
  const supported = passkeysSupported();
  const mayAdd = Boolean(list?.available && list.may_register && supported);

  const start = () => {
    setLabel('');
    setError(null);
    setOpen(true);
  };

  return (
    <>
      <Page
        title="Beveiliging"
        instanceName={instance?.name}
        {...(list?.available ? { lead: purpose(list) } : {})}
      >
        {query.isPending ? <Loading /> : null}
        {query.isError ? (
          <LoadError error={query.error} retry={() => void query.refetch()} />
        ) : null}
        {list ? (
          <>
            {list.available ? (
              <>
                {!supported ? <Quiet>Deze browser kan geen passkeys vastleggen.</Quiet> : null}
                {supported && !list.may_register ? (
                  <Quiet>
                    Je bent nu ingelogd met een passkey. Log in met SSO Rijk om er een bij te maken.
                  </Quiet>
                ) : null}
                {rowError ? <ErrorNotice message={rowError} /> : null}
                {list.items.length === 0 ? (
                  // Nothing yet: the one thing to do stands with the words, not
                  // alone at the far side of an empty page.
                  <Stack gap="related">
                    <nldd-text>Je hebt nog geen passkey.</nldd-text>
                    {mayAdd ? (
                      <nldd-container layout="row">
                        <Button text="Leg een passkey vast" appearance="primary" onClick={start} />
                      </nldd-container>
                    ) : null}
                  </Stack>
                ) : (
                  <>
                    <ActionBar
                      label="Passkeys"
                      actions={
                        mayAdd
                          ? [{ text: 'Leg een passkey vast', onClick: start, primary: true }]
                          : []
                      }
                    />
                    <nldd-table
                      accessible-label="Je passkeys"
                      columns={`minmax(180px,1fr) minmax(160px,1fr) ${ROW_ACTIONS_COLUMN}`}
                      sm-columns={`minmax(140px,1fr) ${ROW_ACTIONS_COLUMN}`}
                    >
                      <nldd-table-row slot="header">
                        <nldd-text-cell text="Passkey" />
                        <nldd-text-cell text="Gebruik" hide-below="md" />
                        <RowActionsHeader />
                      </nldd-table-row>
                      {list.items.map((passkey) => (
                        <nldd-table-row key={passkey.id}>
                          <nldd-text-cell
                            text={passkey.label}
                            supporting-text={`Vastgelegd op ${formatDate(passkey.created_at)}`}
                          />
                          <nldd-text-cell hide-below="md" text={usedText(passkey)} />
                          <RowActions
                            name={`passkey ${passkey.label}`}
                            actions={[
                              {
                                text: 'Trek in',
                                destructive: true,
                                confirm: {
                                  text: `Passkey '${passkey.label}' intrekken?`,
                                  supportingText:
                                    'Je kunt er daarna niet meer mee inloggen of bevestigen. Wat je er eerder mee bevestigde blijft geldig.',
                                  confirmText: 'Trek in',
                                },
                                onSelect: () => {
                                  setRowError(null);
                                  revoke.mutate(passkey.id);
                                },
                              },
                            ]}
                          />
                        </nldd-table-row>
                      ))}
                    </nldd-table>
                  </>
                )}
              </>
            ) : (
              <EmptyNotice text="Passkeys zijn in deze omgeving niet ingesteld" />
            )}
          </>
        ) : null}
      </Page>
      <FormSheet
        open={open}
        title="Leg een passkey vast"
        submitText="Leg vast"
        onSubmit={() => {
          setError(null);
          register.mutate();
        }}
        onClose={() => setOpen(false)}
        busy={register.isPending}
        error={error}
      >
        <FormFields>
          <TextInput
            label="Naam van dit apparaat"
            value={label}
            onChange={setLabel}
            hint="Bijvoorbeeld Laptop of Telefoon. Je apparaat vraagt daarna om je vingerafdruk, gezicht of pincode."
          />
        </FormFields>
      </FormSheet>
    </>
  );
}
