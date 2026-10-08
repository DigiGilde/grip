import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
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

function SyncState({ status }: { status: RoleSyncStatus }) {
  if (!status.wies_configured) {
    return (
      <nldd-inline-dialog
        text="Er is geen koppeling met Wies"
        supporting-text="De lijst met rollen houd je hier zelf bij. Met een koppeling volgt de lijst de rollen uit Wies."
      />
    );
  }
  const run = status.last_run;
  if (!run) {
    return (
      <nldd-inline-dialog
        text="De rollen zijn nog niet opgehaald uit Wies"
        supporting-text="Ophalen vult de lijst met de rollen die Wies kent en koppelt rollen met dezelfde naam."
      />
    );
  }
  if (run.status === 'failed') {
    return (
      <nldd-banner
        variant="critical"
        text={`Ophalen op ${formatDate(run.finished_at)} is mislukt`}
        supporting-text={run.error ?? 'Er is niets gewijzigd.'}
      />
    );
  }
  return (
    <nldd-banner
      variant="success"
      text={`Laatst opgehaald uit Wies op ${formatDate(run.finished_at)}`}
      supporting-text={roleSyncSummary(run.result)}
    />
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
      return updateRole(role.id, { ...body, is_active: active, needs_review: false });
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

/**
 * For the beheerder: the roles a budget line can be staffed in, where they
 * come from, how often each is used, and which were added on the spot and
 * still want a look.
 */
export function RolesAdminPage() {
  const instance = useInstance();
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

  return (
    <>
      <nldd-simple-section>
        <PageHeading text="Rollen" instanceName={instance?.name} />
        <nldd-container gap="32">
          <nldd-container gap="16">
            <nldd-rich-text>
              <p>
                De rol op een begrotingsregel komt uit deze lijst, zodat dezelfde rol overal
                hetzelfde heet en te tellen is. Wie een begroting invult en een rol mist, kan
                die ter plekke toevoegen; zo&apos;n rol staat hier als te beoordelen.
              </p>
            </nldd-rich-text>
            <QueryState query={status}>
              {status.data ? (
                <>
                  {problem ? <nldd-banner variant="critical" text={problem} /> : null}
                  <SyncState status={status.data} />
                  {status.data.wies_configured ? (
                    <nldd-container layout="wrap" gap="16">
                      <Button
                        text="Haal rollen op uit Wies"
                        appearance="primary"
                        loading={sync.isPending}
                        onClick={() => sync.mutate()}
                      />
                    </nldd-container>
                  ) : null}
                </>
              ) : null}
            </QueryState>
          </nldd-container>

          <nldd-container gap="16">
            {review > 0 ? (
              <nldd-banner
                variant="warning"
                text={review === 1 ? '1 rol om te beoordelen' : `${review} rollen om te beoordelen`}
                supporting-text="Toegevoegd bij het invullen van een begroting of overgenomen uit vrije tekst. Bewaar de rol om haar te houden, of voeg haar samen met een rol die al bestond."
              />
            ) : null}
            <nldd-container layout="wrap" gap="16">
              <Button text="Rol toevoegen" onClick={() => setAdding(true)} />
              <SwitchField
                label="Toon ook uitgeschakelde rollen"
                checked={showInactive}
                onChange={setShowInactive}
              />
            </nldd-container>
            <QueryState query={list}>
              <nldd-table
                accessible-label="Rollen"
                columns="minmax(200px,3fr) minmax(140px,1fr) minmax(160px,1fr) 130px 110px"
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Rol" />
                  <nldd-text-cell text="Herkomst" />
                  <nldd-text-cell text="Gebruik" />
                  <nldd-text-cell text="Status" />
                  <nldd-text-cell text="Actie" />
                </nldd-table-row>
                {roles.map((role) => (
                  <nldd-table-row key={role.id}>
                    <nldd-text-cell
                      text={role.name}
                      {...(role.description ? { 'supporting-text': role.description } : {})}
                    />
                    <nldd-text-cell
                      text={sourceText(role)}
                      {...(role.needs_review ? { 'supporting-text': 'Te beoordelen' } : {})}
                    />
                    <nldd-text-cell text={usageText(role.usage_count)} />
                    <nldd-text-cell
                      text={role.is_active ? 'Te kiezen' : 'Uitgeschakeld'}
                      {...(role.is_active ? {} : { color: 'critical' })}
                    />
                    <nldd-cell>
                      <Button
                        size="sm"
                        text="Bewerk"
                        accessibleLabel={`Bewerk ${role.name}`}
                        onClick={() => setOpenId(role.id)}
                      />
                    </nldd-cell>
                  </nldd-table-row>
                ))}
                <EmptyRows
                  text="Er zijn nog geen rollen"
                  supportingText="Voeg een rol toe, of haal de rollen op uit Wies als de koppeling is ingesteld."
                />
              </nldd-table>
            </QueryState>
          </nldd-container>
        </nldd-container>
      </nldd-simple-section>

      <Sheet
        open={adding || opened !== null}
        title={opened ? opened.name : 'Rol toevoegen'}
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
