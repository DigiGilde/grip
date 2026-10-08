import { useRef } from 'react';
import { useAuth } from '@/auth/context';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PATHS } from '@/paths';
import { EmptyNotice, Page } from '@/ui/layout';

const SECTIONS: { path: string; title: string; text: string }[] = [
  {
    path: PATHS.rates,
    title: 'Tarieven',
    text: 'De tarievenkaart per jaar: het maandtarief per categorie en in welke categorie een schaal declareert.',
  },
  {
    path: PATHS.peers,
    title: 'Koppelingen',
    text: 'Opdrachtgevers, opdrachtnemers en corpora waarmee jullie grip berichten uitwisselt.',
  },
  {
    path: PATHS.organisations,
    title: 'Organisaties',
    text: 'De lijst waaruit je een opdrachtgever of opdrachtnemer kiest: ophalen uit het overheidsregister en wat zelf is toegevoegd.',
  },
  {
    path: PATHS.roles,
    title: 'Rollen',
    text: 'De vaste lijst met rollen voor een begrotingsregel: ophalen uit Wies, hernoemen, samenvoegen en wat nog beoordeeld moet worden.',
  },
  {
    path: PATHS.vacancySetup,
    title: 'Vacatureformulier en taalmodel',
    text: 'Het lege aanvraagformulier vacature, de koppeling van de velden en de instelling van het taalmodel.',
  },
  {
    path: PATHS.functionFramework,
    title: 'Functiegebouw Rijk',
    text: 'De functiegroepen met hun schalen, waaruit je kiest bij een vacature.',
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
    <Page title="Beheer" instanceName={instance?.name}>
      {isAdmin ? (
        <div ref={ref}>
          <nldd-list accessible-label="Onderdelen van beheer" appearance="box-base">
            {SECTIONS.map((section) => (
              <nldd-list-item key={section.path} href={section.path}>
                <nldd-text-cell text={section.title} supporting-text={section.text} />
                <nldd-icon-cell size="20" color="secondary" icon="chevron-right" />
              </nldd-list-item>
            ))}
          </nldd-list>
        </div>
      ) : (
        <EmptyNotice
          text="Beheer is voor beheerders"
          supportingText="Heb je hier iets nodig, vraag het dan aan een beheerder. Wie dat zijn zie je onder Team."
        />
      )}
    </Page>
  );
}
