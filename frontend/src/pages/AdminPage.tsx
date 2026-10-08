import { useRef } from 'react';
import { useAuth } from '@/auth/context';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PATHS } from '@/paths';
import { PageHeading } from './PageHeading';

const SECTIONS: { path: string; title: string; text: string }[] = [
  {
    path: PATHS.peers,
    title: 'Koppelingen',
    text: 'Andere instanties en corpora waarmee deze instantie berichten uitwisselt, met het contract per koppeling.',
  },
  {
    path: PATHS.vacancySetup,
    title: 'Vacatureformulier en taalmodel',
    text: 'Het lege aanvraagformulier vacature, de koppeling van de velden en de instelling van het taalmodel.',
  },
  {
    path: PATHS.wiesProposals,
    title: 'Voorstellen uit Wies',
    text: 'Collega’s die volgens Wies erbij moeten of eraf kunnen, ter bevestiging.',
  },
];

/** Where the beheerder finds the settings of the instance. */
export function AdminPage() {
  const instance = useInstance();
  const { state } = useAuth();
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);
  const isAdmin = state.status === 'authenticated' && state.functions.includes('beheerder');

  return (
    <nldd-simple-section>
      <PageHeading text="Beheer" instanceName={instance?.name} />
      {isAdmin ? (
        <div ref={ref}>
          <nldd-list accessible-label="Onderdelen van beheer" appearance="box-base">
            {SECTIONS.map((section) => (
              <nldd-list-item key={section.path} href={section.path}>
                <nldd-text-cell text={section.title} supporting-text={section.text} />
              </nldd-list-item>
            ))}
          </nldd-list>
        </div>
      ) : (
        <nldd-inline-dialog
          text="Beheer is voor de beheerder van deze instantie"
          supporting-text="Je hebt de functie beheerder niet. Personen en functies beheer je onder Team."
        />
      )}
    </nldd-simple-section>
  );
}
