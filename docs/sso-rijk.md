# Inloggen met SSO Rijk

Grip logt in via de Keycloak van het hostingplatform. Die stuurt door naar SSO Rijk. Deze pagina zegt wat daarvan bekend is, wat grip ermee doet, wat nog nooit is uitgevoerd en wat het platform voor grip moet inrichten.

De login is gebouwd naar het voorbeeld van Bouwmeester, dat al langer zo inlogt. Wat hier staat over de keten komt uit de configuratie van het platform en uit de code en de geschiedenis van Bouwmeester, niet uit een eigen aanmelding: die is er nog niet geweest.

## De keten

```
grip -> realm van het project -> realm rig-platform -> SSO Rijk (SAML)
```

De lokale ontwikkelclient `development-clusters` zit rechtstreeks in `rig-platform` en slaat de eerste stap over.

| Onderwerp | Wat de configuratie van het platform zegt |
|---|---|
| E-mailadres bevestigd | De koppeling met SSO Rijk staat op "vertrouw het adres". Een adres uit SSO Rijk komt binnen met `email_verified: true`. |
| Adres zelf wijzigen | E-mailadres, voornaam en achternaam zijn in de accountpagina van Keycloak alleen door een beheerder te wijzigen. Dat is zo sinds een incident waarbij een gebruiker het eigen adres naar dat van een ander kon zetten. Een zelf gewijzigd adres is niet bevestigd. |
| Vaste identiteit (`sub`) | In `rig-platform` is `sub` het kenmerk van SSO Rijk zelf (een urn). In een realm van een project is `sub` het kenmerk van de gebruiker in die realm en staat het kenmerk van SSO Rijk in de claim `sso-rijk-userid`. |
| Overgang van OIDC naar SAML | De overgang hield de gebruikers en hun kenmerk in stand. `sub` verandert alleen als een realm of een gebruiker opnieuw wordt aangemaakt. |
| `preferred_username` | In `rig-platform` het kenmerk van SSO Rijk in kleine letters, geen naam. |
| Organisatie | Naam en nummer van de organisatie gaan mee als `organization.name` en `organization.number`, via een standaard-scope van de realm. Een claim met een punt in de naam komt aan als genest object: `organization: {name, number}`. Dat is lokaal met Keycloak 26 nagegaan. |
| Opnieuw aanmelden | De koppeling met SSO Rijk vraagt bij elke nieuwe aanmelding vanuit Keycloak om opnieuw inloggen (`forceAuthn`). Of `prompt=login` en `max_age=0` van grip door een realm van een project heen bij `rig-platform` aankomen, is niet gemeten. |
| Duur van een sessie | De realm houdt een aanmelding acht uur vast zonder gebruik en twaalf uur in totaal. |

## Wat grip doet

- **Wie binnenkomt.** Alleen een persoon die een beheerder vooraf heeft aangemaakt. Eerst op `sub`; bij een eerste aanmelding op het e-mailadres, en dan alleen als de provider voor dat adres instaat. Het adres wordt vergeleken zonder onderscheid tussen hoofd- en kleine letters. Daarna geldt alleen nog `sub`: een later gewijzigd adres doet niets.
- **Een adres zonder bevestiging telt niet,** ook niet als de claim ontbreekt. Dat is de verdediging tegen het incident hierboven en wordt niet instelbaar gemaakt.
- **Een bekend adres met een ander `sub`** bindt niets opnieuw. De beheerder ontkoppelt de login bij Team; de volgende aanmelding bindt dan weer. Bouwmeester maakt in dat geval een tweede persoon aan; grip doet dat bewust niet.
- **Elke aanmelding staat in de gebeurtenissen,** alleen voor beheer: gelukt (met de regel waarop), als gast, of geweigerd met de reden en het aangeboden adres. Een eerste aanmelding kan zo niet stil mislukken.
- **De naam** komt uit `name`, anders uit voor- en achternaam. Een kenmerk wordt nooit als naam getoond.
- **De organisatie** leest grip uit de claim, genest of plat. Het is wat SSO Rijk heeft vastgelegd, geen feit dat grip heeft gecontroleerd.
- **Terugkomen met een fout** eindigt rustig: wie bij de provider afbreekt komt terug op de loginpagina, een verlopen of mislukte aanmelding ook, en een onbereikbare provider geeft geen foutpagina van de server.
- **Uitloggen** gaat naar het adres dat de provider zelf opgeeft, met de tokens ingetrokken.
- **Een rem** op de aanmeldroute: dertig verzoeken per minuut per adres, per proces.

Redenen van een weigering:

| Code | Betekenis | Wat te doen |
|---|---|---|
| `onbekend` | Geen persoon met dit adres | De beheerder maakt de persoon aan, met het adres zoals SSO Rijk het stuurt |
| `emailadres_niet_bevestigd` | De provider staat niet in voor het adres | Navragen bij het platform; niet omzeilen |
| `andere_aanmelding` | De persoon is aan een andere identiteit gebonden | De login ontkoppelen bij Team |
| `inactief` | De persoon is niet actief | Activeren, als dat de bedoeling is |
| `geen_emailadres`, `geen_subject` | De provider stuurde het niet | Navragen bij het platform |

## Vergeleken met Bouwmeester

| Onderwerp | Bouwmeester | Grip | Keuze |
|---|---|---|---|
| Onbekende persoon | Wordt aangemaakt, daarna een toelatingslijst en een verzoek om plaatsing | Geen toegang | Grip: wie binnen mag is vooraf bepaald |
| Koppelen op adres | Alleen bevestigd, sinds september 2026 | Alleen bevestigd, vanaf het begin | Gelijk |
| Zelfde adres, ander `sub` | Tweede persoon | Weigeren, beheerder ontkoppelt | Grip |
| Meer adressen per persoon | Ja, een eigen tabel | Een adres | Bouwmeester; voor grip pas nodig als het zich voordoet |
| Fout bij terugkomst | Geen afhandeling: een serverfout | Rustige terugkeer met een code | Grip |
| Waar de persoon in de sessie staat | Adres en `sub`, persoon wordt bij status opgezocht | Het id van de persoon, bij elke aanvraag opnieuw geladen | Grip: deactiveren werkt meteen |
| Terugkeeradres | Uit de instelling | Uit de instelling, of de voorkant als de aanvraag daarlangs kwam | Gelijk van strekking |
| Rem op aanmelden | Ja | Nu ook | Overgenomen |
| Uitlogadres | Vast pad van Keycloak | Uit het ontdekkingsdocument | Grip |
| Duur van een sessie | Zeven dagen, met verversen | Volgt het token, met verversen | Gelijk van strekking |
| Opnieuw aanmelden bij een besluit | Niet | Ja, gebonden aan het document | Grip |
| Organisatie uit claims | Niet | Gelezen, niet vertrouwd | Grip |
| Aanmeldingen vastgelegd | Alleen in het logbestand | In de gebeurtenissen | Grip |

Wat Bouwmeester in gebruik leerde en grip al had of nu heeft:

1. Voorvragen van de browser kregen een 401 van de toegangscontrole: die laat ze nu door.
2. Een cookie met het voorvoegsel `__Host-` was vanaf de voorkant niet te lezen, waardoor elke wijziging een 403 gaf: het voorvoegsel is weg.
3. Fouten van tussenlagen kwamen zonder de kopregels voor een andere herkomst bij de browser aan: die laag staat nu buitenom.
4. Een fout in de sessielaag gaf een kale serverfout: afgevangen.
5. Een persoon met twee plaatsingen kon niet inloggen door een zoekvraag die er een verwachtte.
6. De statusvraag slikte fouten in en liet mensen zonder uitleg op de loginpagina staan: ze geeft nu een code.
7. De tijd dat een sessie geldig blijft terwijl de provider onbereikbaar is ging van tien naar twee minuten.
8. Een gebruiker kon gegevens van een ander opvragen met een zelf meegegeven id: het id komt nu uit de sessie.
9. Koppelen op een onbevestigd adres: gestopt na het incident bij het platform.

## De eerste echte aanmelding

Er is een recept dat grip tegen de echte ontwikkelclient start en na een aanmelding toont wat er binnenkwam. Namen, adressen en kenmerken zijn gemaskeerd en tokens staan er niet in, dus het verslag kan gedeeld worden. Zie [lokaal.md](lokaal.md), "Inloggen met SSO Rijk".

Het verslag beantwoordt vier vragen:

1. Meldt de provider het adres als bevestigd?
2. Welk adres komt binnen, en met hoofdletters of zonder?
3. Is de tweede aanmelding met `prompt=login` en `max_age=0` echt een nieuwe (een nieuwer `auth_time`)?
4. Welke claims over de organisatie komen mee, en in welke vorm?

## Verzoeken aan het platform, voor de eigen client van grip

1. **Terugkeeradressen:** `https://<voorkant>/api/auth/callback` en `https://<achterkant>/api/auth/callback`. Het besluit met bewijs komt op hetzelfde adres terug; daar is geen eigen adres voor nodig.
2. **Na uitloggen:** `https://<voorkant>/*` als toegestaan adres.
3. **Scopes:** `openid email profile`, en de scope `custom_attributes_passthrough` als standaard voor de client, zodat de organisatie in het ID-token staat.
4. **`sso-rijk-userid` in het token** van de realm van het project. Grip gebruikt het nog niet, maar het is de enige identiteit die een opnieuw aangemaakte realm overleeft.
5. **Opnieuw aanmelden doorgeven.** In de realm van het project, bij de koppeling naar `rig-platform`: "Pass max_age" aan, en "Prompt" leeg laten zodat `prompt=login` van grip wordt doorgegeven. Keycloak geeft `prompt` van de aanvrager door als het veld leeg is en `max_age` alleen als de schakelaar aan staat. Dat volgt uit de instellingen van Keycloak en is niet gemeten; het verslag hierboven meet het.
6. **PKCE** met S256 verplicht voor de client.
7. **De vraag:** bevestigen dat een adres dat een gebruiker zelf wijzigt nooit als bevestigd aankomt, ook niet via een realm van een project.

## Niet nagegaan

- Een aanmelding via het echte SSO Rijk.
- Of een uitgelogde sessie bij SSO Rijk binnen vijf minuten ook in grip eindigt. Grip controleert het token elke vijf minuten bij de provider.
- De duur van de eigen sessie tegenover de twaalf uur van de realm.
