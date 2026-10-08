import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import {
  Button,
  CheckboxInput,
  EmptyNotice,
  ErrorNotice,
  LinkButton,
  Loading,
  Note,
  SectionHeading,
} from '@/features/vacancies/ui';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import {
  WIES_KEYS,
  confirmChanges,
  fetchReconciliation,
  proposalKey,
  type AppliedChange,
  type PersonProposal,
} from './api';
import { ACTION_LABELS, ACTION_ORDER, GROUP_HEADINGS, describe } from './labels';

function Result({ applied }: { applied: AppliedChange[] }) {
  const done = applied.filter((change) => change.applied).length;
  const skipped = applied.filter((change) => !change.applied);
  return (
    <nldd-container gap="12">
      <nldd-banner
        variant={skipped.length > 0 ? 'warning' : 'success'}
        text={
          skipped.length > 0
            ? `${done} van ${applied.length} wijzigingen doorgevoerd`
            : `${done} wijzigingen doorgevoerd`
        }
      />
      {skipped.length > 0 && (
        <nldd-list accessible-label="Niet doorgevoerde wijzigingen" appearance="box-base">
          {skipped.map((change) => (
            <nldd-list-item key={proposalKey(change)}>
              <nldd-text-cell
                overline={`${ACTION_LABELS[change.action] ?? change.action}: niet doorgevoerd`}
                text={change.email}
                supporting-text={change.reason ?? 'Wies onderbouwt deze wijziging niet meer.'}
              />
            </nldd-list-item>
          ))}
        </nldd-list>
      )}
    </nldd-container>
  );
}

function ProposalGroup({
  heading,
  proposals,
  selected,
  onToggle,
  disabled,
}: {
  heading: string;
  proposals: PersonProposal[];
  selected: Set<string>;
  onToggle: (key: string, checked: boolean) => void;
  disabled: boolean;
}) {
  return (
    <nldd-container gap="8">
      <SectionHeading text={`${heading} (${proposals.length})`} level={3} />
      <nldd-list accessible-label={heading} appearance="box-base">
        {proposals.map((proposal) => {
          const key = proposalKey(proposal);
          return (
            <nldd-list-item key={key}>
              <nldd-cell>
                <CheckboxInput
                  label={`${ACTION_LABELS[proposal.action]}: ${proposal.name}`}
                  checked={selected.has(key)}
                  onChange={(checked) => onToggle(key, checked)}
                  disabled={disabled}
                />
              </nldd-cell>
              <nldd-text-cell text={describe(proposal)} supporting-text={proposal.reason} />
            </nldd-list-item>
          );
        })}
      </nldd-list>
    </nldd-container>
  );
}

/**
 * What Wies proposes for the persons of this instance. Nothing here happens
 * by itself: the beheerder ticks what should be done and confirms. The
 * backend fetches Wies again at that moment and applies only what Wies still
 * backs, so each confirmed change comes back as applied or not, with why.
 */
export function WiesProposalsPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const query = useQuery({
    queryKey: WIES_KEYS.reconciliation,
    queryFn: fetchReconciliation,
    retry: false,
  });
  const confirm = useMutation({
    mutationFn: confirmChanges,
    onSuccess: () => {
      setSelected(new Set());
      void queryClient.invalidateQueries({ queryKey: WIES_KEYS.reconciliation });
      void queryClient.invalidateQueries({ queryKey: ['team'] });
    },
  });

  const proposals = useMemo(() => query.data?.proposals ?? [], [query.data]);
  const groups = ACTION_ORDER.map((action) => ({
    action,
    items: proposals.filter((proposal) => proposal.action === action),
  })).filter((group) => group.items.length > 0);
  const chosen = proposals.filter((proposal) => selected.has(proposalKey(proposal)));

  function toggle(key: string, checked: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
  }

  const data = query.data;
  return (
    <nldd-simple-section>
      <PageHeading text="Voorstellen uit Wies" instanceName={instance?.name} />
      <nldd-container gap="16">
        <RouterLinks>
          <LinkButton text="Terug naar team" href={PATHS.team} appearance="neutral-transparent" />
        </RouterLinks>
        <Note>
          Wies is de bron van mensen. Grip voegt niemand toe en deactiveert niemand uit zichzelf:
          vink aan wat je wilt doorvoeren. Wie wordt toegevoegd kan daarna inloggen.
        </Note>
        {query.isPending && <Loading text="Wies wordt geraadpleegd" />}
        {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
        {data && !data.configured && (
          <EmptyNotice
            text="De koppeling met Wies is niet ingesteld"
            supportingText="Stel in deze instantie het adres en de sleutel van Wies in. Tot die tijd beheer je personen met de hand op de pagina Team."
          />
        )}
        {confirm.isError && <ErrorNotice message={errorMessage(confirm.error)} />}
        {confirm.data && <Result applied={confirm.data} />}
        {data?.configured && (
          <>
            <nldd-text size="sm" color="secondary">
              {`${data.wies_colleagues ?? 0} collega's in Wies`}
              {data.fetched_at ? `, opgehaald op ${formatDate(data.fetched_at)}` : ''}
            </nldd-text>
            {proposals.length === 0 ? (
              <EmptyNotice
                text="Geen voorstellen"
                supportingText={
                  data.note ?? 'De personen in grip komen overeen met de collega\'s in Wies.'
                }
              />
            ) : (
              <>
                {groups.map((group) => (
                  <ProposalGroup
                    key={group.action}
                    heading={GROUP_HEADINGS[group.action]}
                    proposals={group.items}
                    selected={selected}
                    onToggle={toggle}
                    disabled={confirm.isPending}
                  />
                ))}
                <nldd-button-group>
                  <Button
                    text={
                      chosen.length === 0
                        ? 'Voer door'
                        : `Voer ${chosen.length} ${chosen.length === 1 ? 'wijziging' : 'wijzigingen'} door`
                    }
                    appearance="primary"
                    disabled={chosen.length === 0}
                    loading={confirm.isPending}
                    onClick={() =>
                      confirm.mutate(
                        chosen.map((proposal) => ({
                          action: proposal.action,
                          email: proposal.email,
                        })),
                      )
                    }
                  />
                  <Button
                    text="Alles aanvinken"
                    appearance="neutral-transparent"
                    disabled={confirm.isPending}
                    onClick={() => setSelected(new Set(proposals.map(proposalKey)))}
                  />
                </nldd-button-group>
              </>
            )}
          </>
        )}
      </nldd-container>
    </nldd-simple-section>
  );
}
