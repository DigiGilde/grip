import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { EmptyNotice, ErrorNotice, Loading } from '@/features/assignments/ui';
import { QUOTE_STATUS_LABELS } from '@/features/quotes/api';
import { formatDateTime } from '@/features/quotes/format';
import { useInstance } from '@/layout/useInstance';
import { formatDate } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { fetchSigningInvitations, signingKeys } from './api';

/** The quotes someone was invited to sign. */
export function SigningListPage() {
  const instance = useInstance();
  const query = useQuery({
    queryKey: signingKeys.invitations,
    queryFn: fetchSigningInvitations,
  });
  const invitations = query.data?.invitations ?? [];

  return (
    <nldd-simple-section>
      <PageHeading text="Offertes om te tekenen" instanceName={instance?.name} />
      {query.isPending ? <Loading /> : null}
      {query.isError ? <ErrorNotice message={errorMessage(query.error)} /> : null}
      {query.data && invitations.length === 0 ? (
        <EmptyNotice
          text="Er staat geen offerte voor je klaar"
          supportingText="Je ziet hier een offerte zodra iemand je heeft uitgenodigd om die te tekenen. Klopt dit niet, neem dan contact op met wie je de link stuurde."
        />
      ) : null}
      {invitations.length > 0 ? (
        <nldd-table
          accessible-label="Offertes om te tekenen"
          columns="minmax(200px,2fr) minmax(140px,1fr) minmax(120px,1fr) minmax(120px,1fr) 120px"
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Opdracht" />
            <nldd-text-cell text="Uitgegeven" />
            <nldd-text-cell text="Geldig tot en met" />
            <nldd-text-cell text="Status" />
            <nldd-text-cell text="Actie" />
          </nldd-table-row>
          {invitations.map((invitation) => (
            <nldd-table-row key={invitation.quote_id}>
              <nldd-text-cell text={invitation.assignment_name} />
              <nldd-text-cell text={formatDateTime(invitation.issued_at)} />
              <nldd-text-cell text={formatDate(invitation.valid_until) || 'Geen einddatum'} />
              <nldd-text-cell text={QUOTE_STATUS_LABELS[invitation.status] ?? invitation.status} />
              <nldd-cell>
                <nldd-link
                  href={`/tekenen/${invitation.quote_id}`}
                  text="Open"
                  size="md"
                  accessible-label={`Open de offerte voor ${invitation.assignment_name}`}
                />
              </nldd-cell>
            </nldd-table-row>
          ))}
        </nldd-table>
      ) : null}
    </nldd-simple-section>
  );
}
