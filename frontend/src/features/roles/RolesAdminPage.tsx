import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { RouterLinks } from '@/layout/RouterLinks';
import { ActionBar } from '@/ui/ActionBar';
import { Page, Quiet } from '@/ui/layout';
import { OpenCell, OpenRow } from '@/ui/RowActions';
import { Button, SwitchField, TextField } from '@/features/team/ui/controls';
import { ConfirmDialog, Form, Sheet } from '@/features/team/ui/overlays';
import { EmptyRows, QueryState } from '@/features/team/ui/states';
import {
  createRole,
  fetchRoleSync,
  fetchRoles,
  mergeRole,
  roleKeys,
  runRoleSync,
  updateRole,
  type CatalogueRole,
  type RoleSyncStatus,
} from './api';
import { RolePicker } from './RolePicker';
import { roleSyncSummary, sourceText, usageText } from './text';
import './nldd';
import { useAdminBack } from '@/layout/useAdminBack';

/** When the list last followed Wies, as one quiet line; a failure as a problem. */
function SyncState({ status }: { status: RoleSyncStatus }) {
  const run = status.last_run;
  if (!status.wies_configured || !run) return null;
  if (run.status === 'failed') {
    // A state, not an alarm: the list is as it was, and fetching again is
    // the one thing to do about it.
    return (
      <Quiet>
        De rollen uit Wies zijn op {formatDate(run.finished_at)} niet opgehaald
        {run.error ? ` (${run.error})` : ''}. De lijst is ongewijzigd. Haal de rollen opnieuw op als
        Wies weer bereikbaar is.
      </Quiet>
    );
  }
  return (
    <Quiet>
      Laatst opgehaald uit Wies op {formatDate(run.finished_at)}: {roleSyncSummary(run.result)}
    </Quiet>
  );
}

interface RoleSheetProps {
  /** The role to change; null to add one. */
  role: CatalogueRole | null;
  onDone: () => void;
}

function RoleForm({ role, onDone }: RoleSheetProps) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(role?.name ?? '');
  const [description, setDescription] = useState(role?.description ?? '');
  const [active, setActive] = useState(role?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => {
      const body = { name: name.trim(), description: description.trim() || null };
      if (!role) return createRole(body);
      // Saving a role is also how the beheerder says it has been looked at.
      return updateRole(role.id, { ...body, is_active: active, needs_review: false }, role.version);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: roleKeys.all });
      onDone();
    },
    onError: (err) => setError(errorMessage(err)),
  });

  return (
    <Form
      submitText={role ? 'Bewaar' : 'Voeg toe'}
      submitting={save.isPending}
      error={error}
      onSubmit={() => {
        if (!name.trim()) {
          setError('Geef de rol een naam.');
          return;
        }
        save.mutate();
      }}
    >
      <TextField
        label="Naam"
        supportingLabel={
          role && role.usage_count > 0
            ? `Hernoemen past de naam aan op ${usageText(role.usage_count)}. Offertes die al zijn uitgegeven houden de oude naam.`
            : 'Zoals de rol op een begrotingsregel en in Wies heet'
        }
        value={name}
        onChange={setName}
        required
      />
      <TextField
        label="Toelichting"
        supportingLabel="Wat iemand in deze rol doet, voor wie tussen twee rollen twijfelt"
        optional
        value={description}
        onChange={setDescription}
      />
      {role ? (
        <SwitchField
          label="Te kiezen op een begrotingsregel"
          checked={active}
          onChange={setActive}
        />
      ) : null}
    </Form>
  );
}

function MergeForm({ role, onDone }: { role: CatalogueRole; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<CatalogueRole | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const merge = useMutation({
    mutationFn: () => mergeRole(role.id, target?.id ?? ''),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: roleKeys.all });
      setConfirming(false);
      onDone();
    },
    onError: (err) => {
      setConfirming(false);
      setError(errorMessage(err));
    },
  });

  return (
    <nldd-container gap="16">
      <nldd-title size={4} text="Samenvoegen" heading-level={2} />
      <nldd-rich-text>
        <p>
          Betekent deze rol hetzelfde als een andere, voeg ze dan samen. De begrotingsregels van
          &quot;{role.name}&quot; krijgen de andere rol en &quot;{role.name}&quot; verdwijnt uit de
          lijst.
        </p>
      </nldd-rich-text>
      {error ? <nldd-banner variant="critical" text={error} /> : null}
      <RolePicker
        label="Voeg samen met"
        value={target?.name ?? null}
        onChange={setTarget}
        allowAdd={false}
        exclude={[role.id]}
      />
      <nldd-container layout="wrap" gap="16">
        <Button
          text="Voeg samen"
          appearance="destructive"
          disabled={target === null}
          onClick={() => setConfirming(true)}
        />
      </nldd-container>
      <ConfirmDialog
        open={confirming}
        text={`"${role.name}" samenvoegen met "${target?.name ?? ''}"?`}
        supportingText={`${usageText(role.usage_count)} van "${role.name}" ${role.usage_count === 1 ? 'krijgt' : 'krijgen'} de rol "${target?.name ?? ''}". Dit is niet terug te draaien.`}
        confirmText="Voeg samen"
        destructive
        onConfirm={() => merge.mutate()}
        onClose={() => setConfirming(false)}
      />
    </nldd-container>
  );
}

const SHOW_OPTIONS = [
  { value: 'active', label: 'Rollen die te kiezen zijn' },
  { value: 'all', label: 'Ook uitgeschakelde rollen' },
] as const;

/**
 * For the beheerder: the roles a budget line can be staffed in, where they
 * come from, how often each is used, and which were added on the spot and
 * still want a look.
 */
export function RolesAdminPage() {
  const instance = useInstance();
  const adminBack = useAdminBack();
  const queryClient = useQueryClient();
  const [showInactive, setShowInactive] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const list = useQuery({
    queryKey: roleKeys.list(showInactive),
    queryFn: () => fetchRoles(showInactive),
  });
  const status = useQuery({ queryKey: roleKeys.sync, queryFn: fetchRoleSync });
  const roles = list.data?.items ?? [];
  const opened = roles.find((role) => role.id === openId) ?? null;
  const review = roles.filter((role) => role.needs_review && role.is_active).length;

  const sync = useMutation({
    mutationFn: runRoleSync,
    onSuccess: async (next) => {
      setProblem(null);
      queryClient.setQueryData(roleKeys.sync, next);
      await queryClient.invalidateQueries({ queryKey: roleKeys.all });
    },
    onError: (error) => setProblem(errorMessage(error)),
  });
  const close = () => {
    setOpenId(null);
    setAdding(false);
  };

  // What still wants a look comes first; a role from one source only says
  // nothing by naming that source on every row.
  const ordered = [...roles].sort(
    (a, b) =>
      Number(b.needs_review && b.is_active) - Number(a.needs_review && a.is_active) ||
      a.name.localeCompare(b.name, 'nl'),
  );
  const mixedSource = new Set(roles.map((role) => role.source)).size > 1;
  const columns = [
    'minmax(200px,3fr)',
    ...(mixedSource ? ['minmax(120px,1fr)'] : []),
    'minmax(160px,1fr)',
    '150px',
  ].join(' ');

  return (
    <>
      <RouterLinks>
        <Page title="Rollen" instanceName={instance?.name} back={adminBack}>
          <ActionBar
            label="Rollen filteren en acties"
            filters={[
              {
                label: 'Toon',
                value: showInactive ? 'all' : 'active',
                onChange: (value) => setShowInactive(value === 'all'),
                options: SHOW_OPTIONS,
                width: '260px',
              },
            ]}
            actions={[
              ...(status.data?.wies_configured
                ? [{ text: 'Haal rollen op uit Wies', onClick: () => sync.mutate() }]
                : []),
              { text: 'Nieuwe rol', onClick: () => setAdding(true), primary: true },
            ]}
          />
          {problem ? <nldd-banner variant="critical" text={problem} /> : null}
          {status.data ? <SyncState status={status.data} /> : null}
          {review > 0 ? (
            <nldd-text>
              {review === 1
                ? 'Eén rol is ter plekke toegevoegd en nog niet beoordeeld.'
                : `${review} rollen zijn ter plekke toegevoegd en nog niet beoordeeld.`}
            </nldd-text>
          ) : null}
          <QueryState query={list}>
            <nldd-table
              accessible-label="Rollen"
              columns={columns}
              sm-columns="minmax(160px,1fr) 130px"
            >
              <nldd-table-row slot="header">
                <nldd-text-cell text="Rol" />
                {mixedSource ? <nldd-text-cell text="Herkomst" hide-below="md" /> : null}
                <nldd-text-cell text="Gebruik" hide-below="md" />
                <nldd-cell />
              </nldd-table-row>
              {ordered.map((role) => (
                <OpenRow key={role.id} onOpen={() => setOpenId(role.id)}>
                  <OpenCell
                    text={role.name}
                    {...(role.description ? { supportingText: role.description } : {})}
                    accessibleLabel={`Bewerk ${role.name}`}
                    onOpen={() => setOpenId(role.id)}
                  />
                  {mixedSource ? <nldd-text-cell text={sourceText(role)} hide-below="md" /> : null}
                  <nldd-text-cell
                    text={usageText(role.usage_count)}
                    hide-below="md"
                    {...(role.usage_count === 0 ? { color: 'secondary' } : {})}
                  />
                  {/* A label only for what differs from the rule: a role is
                      there to be chosen. */}
                  <nldd-cell>
                    {!role.is_active ? (
                      <nldd-tag color="neutral" text="Uitgeschakeld" />
                    ) : role.needs_review ? (
                      <nldd-tag color="warning" text="Te beoordelen" />
                    ) : null}
                  </nldd-cell>
                </OpenRow>
              ))}
              <EmptyRows text="Er zijn nog geen rollen" />
            </nldd-table>
          </QueryState>
        </Page>
      </RouterLinks>
      <Sheet
        open={adding || opened !== null}
        title={opened ? opened.name : 'Nieuwe rol'}
        dismissText={opened ? 'Sluit' : 'Annuleer'}
        onClose={close}
      >
        {adding || opened ? (
          <nldd-container gap="32">
            <RoleForm key={opened?.id ?? 'new'} role={opened} onDone={close} />
            {opened ? <MergeForm key={`merge-${opened.id}`} role={opened} onDone={close} /> : null}
          </nldd-container>
        ) : null}
      </Sheet>
    </>
  );
}
