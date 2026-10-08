import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { QUOTE_STATUS_LABELS } from '@/features/quotes/api';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatDate } from '@/lib/format';
import { EmptyNotice, ErrorNotice, Loading, Page } from '@/ui/layout';
import { fetchSigningInvitations, signingKeys } from './api';

/** What the reader can do with a quote, in the word of the action. */
function actionText(status: string): string {
  return status === 'issued' ? 'Bekijk en teken' : 'Bekijk';
}

/** The quotes someone was invited to sign. */
export function SigningListPage() {
  const instance = useInstance();
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);
  const query = useQuery({
    queryKey: signingKeys.invitations,
    queryFn: fetchSigningInvitations,
  });
  const invitations = query.data?.invitations ?? [];

  return (
    <Page title="Offertes om te tekenen" instanceName={instance?.name} width="960px">
      {query.isPending ? <Loading /> : null}
      {query.isError ? <ErrorNotice message={errorMessage(query.error)} /> : null}
      {query.data && invitations.length === 0 ? (
        <EmptyNotice
          text="Er staat geen offerte voor je klaar"
          supportingText="Verwacht je er een, vraag dan degene die je de link stuurde om je opnieuw uit te nodigen."
        />
      ) : null}
      {invitations.length > 0 ? (
        <div ref={ref}>
          <nldd-table
            accessible-label="Offertes om te tekenen"
            columns="minmax(220px,2fr) minmax(130px,1fr) minmax(130px,1fr) max-content"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Offerte" />
              <nldd-text-cell text="Geldig tot en met" />
              <nldd-text-cell text="Stand" />
              <nldd-text-cell text="Actie" />
            </nldd-table-row>
            {invitations.map((invitation) => (
              <nldd-table-row key={invitation.quote_id}>
                <nldd-text-cell
                  text={invitation.assignment_name}
                  supporting-text={[invitation.reference, `gemaakt op ${formatDate(invitation.issued_at)}`]
                    .filter(Boolean)
                    .join(' · ')}
                />
                <nldd-text-cell text={formatDate(invitation.valid_until) || 'Geen einddatum'} />
                <nldd-text-cell
                  text={
                    invitation.status === 'issued'
                      ? 'Wacht op je akkoord'
                      : (QUOTE_STATUS_LABELS[invitation.status] ?? invitation.status)
                  }
                />
                <nldd-cell>
                  <nldd-link
                    href={`/tekenen/${invitation.quote_id}`}
                    text={actionText(invitation.status)}
                    size="md"
                    accessible-label={[
                      `${actionText(invitation.status)}: offerte`,
                      invitation.reference,
                      `voor ${invitation.assignment_name}`,
                    ]
                      .filter(Boolean)
                      .join(' ')}
                  />
                </nldd-cell>
              </nldd-table-row>
            ))}
          </nldd-table>
        </div>
      ) : null}
    </Page>
  );
}
