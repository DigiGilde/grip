import { useRef } from 'react';
import { useAuth } from '@/auth/context';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PATHS } from '@/paths';
import { IconCell } from '@/ui/Icon';
import { Page, Section, Stack, NoAccess } from '@/ui/layout';

interface Entry {
  path: string;
  title: string;
  /** What it is, in a few words. */
  text: string;
}

/**
 * Grouped by what a beheerder comes to do. A new page under Beheer is one
 * entry in the group it belongs to.
 */
const GROUPS: { title: string; entries: Entry[] }[] = [
  {
    title: 'Mensen en rollen',
    entries: [
      {
        path: PATHS.wiesProposals,
        title: 'Voorstellen uit Wies',
        text: 'Collega’s die erbij moeten of eraf kunnen',
      },
      { path: PATHS.roles, title: 'Rollen', text: 'De rollen voor een begrotingsregel' },
      {
        path: PATHS.functionFramework,
        title: 'Functiegebouw Rijk',
        text: 'Functiegroepen met hun schalen',
      },
    ],
  },
  {
    title: 'Geld',
    entries: [{ path: PATHS.rates, title: 'Tarieven', text: 'Tarievenkaarten en schalen' }],
  },
  {
    title: 'Documenten en teksten',
    entries: [
      {
        path: PATHS.quoteSender,
        title: 'Afzender en teksten van offertes',
        text: 'Wie de offerte stuurt en wat er standaard in staat',
      },
      { path: PATHS.quoteSettings, title: 'Offertes', text: 'Kenmerk, goedkeuring en mail' },
      {
        path: PATHS.vacancySetup,
        title: 'Aanvraagformulier',
        text: 'Het lege formulier voor een vacature en wat grip erin invult',
      },
      {
        path: PATHS.vacancyStandardTexts,
        title: 'Standaardteksten voor vacatures',
        text: 'De tekst per rol en de gedeelde onderdelen',
      },
    ],
  },
  {
    title: 'Verbindingen',
    entries: [
      {
        path: PATHS.peers,
        title: 'Koppelingen',
        text: 'Instanties en corpora waarmee grip berichten uitwisselt',
      },
      {
        path: PATHS.organisations,
        title: 'Organisaties',
        text: 'Het overheidsregister en wat zelf is toegevoegd',
      },
      {
        path: PATHS.languageModel,
        title: 'Taalmodel',
        text: 'Het model dat teksten voorstelt, en wat ernaartoe gaat',
      },
      {
        path: PATHS.client,
        title: 'Aanvragen als opdrachtgever',
        text: 'Offertes aanvragen en ontvangen offertes',
      },
    ],
  },
  {
    title: 'Toezicht',
    entries: [
      { path: PATHS.activity, title: 'Activiteit', text: 'Wie wat heeft gewijzigd of ingezien' },
    ],
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
    <Page title="Beheer" instanceName={instance?.name} spacing="sections">
      {isAdmin ? (
        <div ref={ref}>
          <Stack gap="section">
            {GROUPS.map((group) => (
              <Section key={group.title} title={group.title}>
                <nldd-list accessible-label={group.title} appearance="box-base">
                  {group.entries.map((entry) => (
                    <nldd-list-item key={entry.path} href={entry.path}>
                      <nldd-text-cell text={entry.title} supporting-text={entry.text} />
                      <IconCell concept="open" />
                    </nldd-list-item>
                  ))}
                </nldd-list>
              </Section>
            ))}
          </Stack>
        </div>
      ) : (
        <NoAccess who="Beheer is voor beheerders. Heb je hier iets nodig, vraag het dan aan een beheerder. Wie dat zijn zie je onder Team." />
      )}
    </Page>
  );
}
