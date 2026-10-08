# Lokale omgeving

Grip draait op je eigen machine zoals het straks op het platform draait: gebouwde images achter nginx, met een echte login en met FSC tussen twee instanties. Deze pagina beschrijft hoe je dat start en wat ermee is aangetoond.

Dit is iets anders dan `just dev`. Dat start de ontwikkelopzet met hot reload op poort 5183. De lokale omgeving hier is een eigen compose-project (`grip-local`) op poorten vanaf 9000, met eigen databases. De twee zitten elkaar niet in de weg.

Alles staat in `deploy/local/`. Wat per machine wordt gegenereerd (certificaten, sleutels, wachtwoorden) komt in `deploy/local/state/` en staat niet in de repo.

## Starten

Je hebt Docker nodig, verder niets.

```
just local-build        # de twee images bouwen
just local-up           # een instantie, zonder login
just local-urls         # waar alles luistert
just local-down         # stoppen, gegevens blijven
just local-nuke         # stoppen en alles van deze omgeving weggooien
```

`just local-build head` bouwt vanaf de laatste commit in plaats van vanaf je werkmap. Dat is handig als je midden in een wijziging zit die nog niet bouwt.

| Modus | Wat je krijgt |
|---|---|
| `just local-up` | Een instantie op http://localhost:9001, ingelogd als plaatsvervangende beheerder |
| `just local-up keycloak` | Dezelfde instantie met een echte login via een lokale Keycloak |
| `just local-up sso` | Dezelfde instantie met login via SSO Rijk |
| `just local-up fsc` | Twee instanties met FSC ertussen |
| `just local-up fsc-keycloak` | Hetzelfde, met de lokale Keycloak |
| `just local-up fsc-corpus` | Twee instanties met FSC, plus een derde deelnemer voor de lokale Bouwmeester |

## Een instantie

Er draaien drie containers: de database, de backend en nginx met de frontend. nginx geeft `/api` door aan de backend, zodat pagina's en API op hetzelfde adres staan. De backend voert bij het starten de migraties uit.

De backend gelooft doorgestuurde headers alleen van nginx. Daarvoor heeft het compose-netwerk een vast adresbereik, dat in `TRUSTED_PROXIES` staat. Zonder die instelling bouwt de backend het adres waarnaar de login terugkeert verkeerd op.

Het backend-image kan vier processen draaien. `GRIP_PROCESS` of het eerste argument kiest welke:

| Proces | Wat het doet |
|---|---|
| `web` | De applicatie voor mensen, op poort 8080. Voert eerst de migraties uit |
| `federation` | De routes die andere organisaties aanroepen, op poort 8090. Alleen de inway mag erbij |
| `worker` | De achtergrondlussen die berichten versturen |
| `all` | `web`, met de andere twee erbij als federatie aan staat. Voor een platform dat per instantie een backendcontainer geeft |

## Inloggen via de lokale Keycloak

`just local-up keycloak` zet er een Keycloak bij met een realm, een client en twee fictieve mensen. Het script `setup.sh` maakt die realm en de wachtwoorden aan; ze staan in `deploy/local/state/secrets.env`.

| Gebruiker | Wat er gebeurt |
|---|---|
| `testbeheerder` | Bekend in grip als beheerder. Komt binnen |
| `onbekend` | Niet bekend in grip. Krijgt de pagina "geen toegang" |

De Keycloak staat op https://localhost:9443 met een certificaat van een eigen lokale CA. Je browser waarschuwt daar een keer voor. Dat TLS is geen versiering: grip stuurt geen tokens naar een identiteitsprovider over gewoon http, ook lokaal niet. De backend vertrouwt de lokale CA via een bundel waarin ook de publieke CA's staan.

`deploy/local/local.sh check-login` doorloopt de hele login met curl, zoals een browser dat doet: doorsturen naar de provider, het inlogformulier, terug met een code, de sessie, de status als die persoon, en uitloggen. Met `check-login onbekend` zie je het pad voor iemand die grip niet kent.

Een ding om te weten: grip bindt een persoon bij de eerste login aan het kenmerk dat de provider voor die persoon gebruikt. De lokale Keycloak bewaart niets, dus de twee gebruikers hebben een vast kenmerk in de realm. Verander je dat, dan komt de persoon er niet meer in tot je de binding in de database leegmaakt.

## Inloggen met SSO Rijk

Het platform heeft een gedeelde OIDC-client voor lokale ontwikkeling: `development-clusters`, in de realm `rig-platform` van de productie-Keycloak. Die realm stuurt je door naar SSO Rijk. De client staat terugkeeradressen op `http://localhost:*/*` toe, dus het adres van de lokale instantie past zonder dat iemand de client hoeft aan te passen.

1. Kopieer `deploy/local/.env.sso.example` naar `deploy/local/.env.sso`.
2. Vul het clientgeheim in. Een beheerder van de realm haalt het uit de beheerconsole van Keycloak: realm `rig-platform`, Clients, `development-clusters`, tabblad Credentials.
3. Vul twee sessiesleutels in (`openssl rand -hex 32`) en je eigen e-mailadres bij `BOOTSTRAP_BEHEERDER_EMAILS`.
4. `just local-up sso` en open http://localhost:9001.

Dit pad is voorbereid maar nog niet uitgevoerd: daarvoor is het geheim nodig.

### De eerste keer: kijken wat er binnenkomt

`just sso-check` start alleen de achterkant, rechtstreeks uit de werkmap, tegen dezelfde `.env.sso` en met een eigen lege database (`grip_sso_check` in de Postgres van `docker compose`). Er zijn geen images voor nodig.

1. `just sso-check`
2. Open http://localhost:9011/api/auth/login en log in met SSO Rijk. Je komt uit op een verslag in platte tekst.
3. Open http://localhost:9011/api/auth/diagnose/reauth. Grip stuurt je opnieuw naar de provider met de vraag om opnieuw aan te melden. Let op of je echt opnieuw moet inloggen.
4. Het verslag staat op http://localhost:9011/api/auth/diagnose. Stop met Ctrl+C.

Het verslag toont welke claims er kwamen, of het adres als bevestigd is gemeld, de vorm van de vaste identiteit, de claims over de organisatie, wat grip met de aanmelding deed (ook bij een weigering, met de reden) en of de tweede aanmelding een nieuwer tijdstip van aanmelden had. Namen, adressen en kenmerken zijn gemaskeerd en tokens staan er niet in: het verslag kan gedeeld worden.

De pagina bestaat alleen met `OIDC_DIAGNOSTICS=1`, en grip weigert te starten als dat in een uitgerolde omgeving aan staat. De cookie van deze sessie staat op `localhost` en heet hetzelfde als die van een andere lokale grip; log daar na afloop zo nodig opnieuw in.

Wat de provider volgens de configuratie van het platform stuurt, en wat het platform voor grip moet inrichten, staat in [sso-rijk.md](sso-rijk.md).

De lokale Keycloak (`just local-up keycloak`) heeft drie gebruikers om de paden te zien: `testbeheerder` (bekend, met een organisatie in de claims), `onbekend` (geen persoon in grip) en `onbevestigd` (bekend in grip, maar de provider staat niet in voor het adres).

## Twee instanties met FSC

`just local-up fsc` start een tweede instantie en FSC tussen de twee, in een eigen groep met eigen certificaten. Er is niets van PKIoverheid bij.

| | Instantie A | Instantie B |
|---|---|---|
| Naam | DigiGilde voorbeeld | Voorbeeldministerie |
| Rol | opdrachtnemer | opdrachtgever |
| Adres | http://localhost:9001 | http://localhost:9002 |
| Peer-id | 01700000000000000001 | 01700000000000000002 |
| FSC-controller | http://localhost:9101 | http://localhost:9102 |

Per deelnemer draaien een manager, een controller, een inway, een outway en een transactielog, elk met een eigen database. Voor de groep draait een directory: een manager die publicaties automatisch tekent, met zijn controller op http://localhost:9100. De images zijn Open FSC 2.8.0, de huidige naam van wat FSC NLX heette. De auditlog gaat naar de containerlog; het losse auditlog-onderdeel is weggelaten.

Aan de kant van grip komen er per instantie twee processen bij: de federatielistener, zonder poort naar buiten, en de worker.

Als alles draait:

```
just local-fsc-init                    # diensten, contracten en het peerregister
deploy/local/local.sh check-fsc        # een bericht van B naar A
```

`local-fsc-init` doet vier dingen, en je kunt het opnieuw draaien:

1. Elke deelnemer registreert de dienst `grip-opdrachtverkeer`, met als doel de eigen federatielistener achter de eigen inway.
2. Elke deelnemer publiceert die dienst in de directory.
3. Elke deelnemer vraagt een verbinding aan met de dienst van de ander, voor de eigen outway, en de ander accepteert.
4. De grant-hashes komen in het peerregister van grip.

`check-fsc` zet een aanvraag in de outbox van instantie B. De worker van B stuurt die via de outway van B en de inway van A naar de federatielistener van A, die hem in de inbox bewaart. Het script toont de regel in de outbox en de regel in de inbox.

De inway geeft de aanroeper door in de header `Fsc-Request-Peer-Id`. Dat is op het netwerk vastgesteld en het is de naam die grip verwacht. De inway stuurt ook `Fsc-Authorization` met het toegangstoken door naar de dienst; die header hoort niet in een log.

### Certificaten

`fsc-pki.sh` maakt twee soorten vertrouwen, zoals FSC voorschrijft:

- Een groeps-CA die alle deelnemers delen. Een groepscertificaat draagt het peer-id in het veld `serialNumber` van het onderwerp en de naam van de organisatie in `O`.
- Een interne CA per deelnemer, voor het verkeer tussen de eigen onderdelen.

De CA zelf heeft ook een organisatie in het onderwerp nodig. Zonder weigert de inway elke aanroeper.

Maak je de certificaten opnieuw (`fsc-pki.sh --fresh`), gooi dan ook de FSC-databases weg: de contracten zijn met de oude sleutels getekend. `just local-nuke` doet beide.

## Bouwmeester en Wies ernaast

Grip staat niet alleen. De context van een opdracht komt uit een corpus in Bouwmeester, en de mensen komen uit Wies. Beide draaien lokaal mee, vanuit hun eigen checkout.

Wat je uitgecheckt moet hebben:

| Repository | Branch | Eenmalig in de checkout |
|---|---|---|
| Bouwmeester | `feat/opdrachten-bij-node` (bevat ook `feat/corpus-context`) | `uv sync` in `backend/`, `npm install` in `frontend/` |
| Wies | `feat/grip-koppeling` | `uv sync` |

Van geen van beide wordt een image gebouwd. De applicaties draaien op je machine vanuit de checkout; alleen hun database is een container. De poorten zijn zo gekozen dat een eigen Bouwmeester op 5433, 8000 en 5173 blijft werken.

| Onderdeel | Adres | Starten | Stoppen |
|---|---|---|---|
| Bouwmeester | http://localhost:9220 | `just bouwmeester-up <checkout>` | `just bouwmeester-down` |
| Wies | http://localhost:9310 | `just wies-up <checkout>` | `just wies-down` |
| Dev outway en de federatielistener van grip | poort 9230 en 9231 | `just dev-link-up` | `just dev-link-down` |

Het pad naar de checkout geef je de eerste keer mee; daarna is het onthouden. Logbestanden staan in `deploy/local/state/`.

### Bouwmeester

`just bouwmeester-up` start de database, voert de migraties uit, laadt de voorbeeldgegevens van Bouwmeester zelf, en start de backend, de dienst corpus-context en de frontend. Zonder de sleutel van de versleutelde personenlijst maakt de seed van Bouwmeester plaatshouders voor personen; er gaat niets naar buiten.

Het corpus heet `https://corpus.voorbeeldministerie.localhost`. Dat adres ziet eruit als een duurzaam domein en bestaat nergens: grip bereikt het corpus via zijn outway, zoals in het echt.

### Grip en Bouwmeester zonder FSC

Voor dagelijks ontwikkelen is een volledige FSC-groep te zwaar. De dev outway (`backend/grip/dev/dev_outway.py`) doet wat een outway en een inway samen doen: hij zoekt de grant hash van een verzoek op in een routesbestand, stuurt het verzoek door naar de dienst van de andere partij en zet het peer-id van de aanroeper in de header die een echte inway zet. Beide applicaties draaien daardoor hun echte federatiecode. Het routesbestand is het hele vertrouwensmodel, dus dit hoort alleen op je eigen machine.

```
just bouwmeester-up <checkout>
just dev-link-up
just dev-link-peers
```

`dev-link-peers` meldt grip aan in Bouwmeester (rol grip) en Bouwmeester in grip (rol corpus, op de basis-URI van het corpus). Een grant hash is hier gewoon een naam die beide kanten kennen.

Daarna start je de backend van grip met de outway erbij:

```
cd backend
env $(../deploy/local/dev-link.sh env) uv run uvicorn grip.core.app:create_app --factory --port 8010
```

Een verzoek met een grant hash die de dev outway niet kent gaat door naar het stand-in corpus van `just corpus-standin`. Opdrachten die naar dat corpus verwijzen blijven dus werken.

De federatielistener van grip leest de database die je opgeeft met `GRIP_DATABASE_URL`; dat moet dezelfde zijn als die van je backend. Met `DEV_LINK_SOURCE=head` draait de listener vanaf de laatste commit in plaats van vanaf je werkmap.

Wat je ziet:

- In grip, op het tabblad Context van een opdracht: de nodes uit Bouwmeester met hun keten naar de politieke input.
- In Bouwmeester, op de pagina van een doel, instrument of maatregel: de kaart "Opdrachten in grip" met fase, periode, begroot en besteed.

Een beperking: Bouwmeester toont alleen opdrachten waarvan opdrachtgever en opdrachtnemer een TOOI-URI hebben, want het contract eist die. De voorbeeldgegevens van `just seed` gebruiken eigen fictieve adressen voor organisaties; daarmee weigert de listener van grip het eigen antwoord.

### Wies

`just wies-up` start de database, voert de migraties uit, laadt de kleine set voorbeeldgegevens van Wies en start de website. Je bent ingelogd als de eerste beheerder. De twee sleutels van de koppeling worden gegenereerd in `deploy/local/state/wies/keys.env`.

```
cd backend
env $(../deploy/local/wies.sh env) $(../deploy/local/dev-link.sh env) uv run uvicorn grip.core.app:create_app --factory --port 8010
```

Daarna:

- Grip leest collega's en vaardigheden uit Wies. Onder Beheer staat het voorstel om de personen bij te werken; `just sync-roles` neemt de vaardigheden over als rollen.
- `just wies-sync` laat Wies opdrachten, rollen en plaatsingen uit grip ophalen. Open rollen staan daarna in Wies onder Aanvragen.
- Een aanstaande collega in grip staat na de sync in Wies onder "Voorstellen uit grip" op `/beheer/database/`.

De voorbeeldgegevens van grip en van Wies kennen elkaars mensen niet. Het voorstel in grip is daarom "iedereen toevoegen, iedereen uitschakelen", en Wies neemt de rollen over maar geen plaatsingen. Dat is juist: de sync maakt nooit zelf een persoon aan.

### Bouwmeester als derde deelnemer in FSC

`just local-up fsc-corpus` voegt een derde deelnemer aan de groep toe, met een eigen manager, controller, inway, outway en transactielog. Bouwmeester zelf blijft op je machine draaien: de inway van deze deelnemer bereikt daar de dienst corpus-context, en Bouwmeester bereikt de outway op http://localhost:9240.

| | Deelnemer C |
|---|---|
| Naam | Corpus Voorbeeldministerie |
| Peer-id | 01700000000000000003 |
| Dienst | `corpus-context` |
| FSC-controller | http://localhost:9103 |

```
just bouwmeester-up <checkout>
just local-up fsc-corpus
just local-fsc-init
just local-fsc-corpus-init
```

`local-fsc-corpus-init` publiceert `corpus-context` vanaf de inway van deelnemer C, sluit contracten in beide richtingen (de grip-instanties naar `corpus-context`, deelnemer C naar `grip-opdrachtverkeer` van elke grip-instantie), zet het corpus in het peerregister van grip en de grip-instanties in de peertabel van Bouwmeester.

Bouwmeester heeft een adres voor zijn outway. Draait de dev outway, dan geeft die de grant hashes van FSC door aan de echte outway van deelnemer C. Zo toont dezelfde Bouwmeester de grip waar je aan ontwikkelt en de grips achter FSC naast elkaar. Zonder dev outway start je Bouwmeester met `BOUWMEESTER_OUTWAY_URL=http://localhost:9240`.

## Mail

Grip mailt de tekenlink van een offerte aan wie wordt uitgenodigd om te tekenen ([ADR 0031](adr/0031-tekenlink-per-mail.md)). Lokaal vangt een mailvanger alles op: wat grip verstuurt komt in zijn postvak en gaat nergens anders heen.

```sh
just mail-up                     # de mailvanger; het postvak staat op http://127.0.0.1:9326
eval "$(deploy/local/mail.sh env)"   # SMTP_HOST, SMTP_PORT, SMTP_FROM, SMTP_TLS=none
just worker-with-mail            # de worker verstuurt wat in de wachtrij staat
just mail-down
```

De backend heeft dezelfde instellingen nodig als de worker: zonder `SMTP_HOST` en `SMTP_FROM` zet hij niets in de wachtrij. Zet `FRONTEND_URL` op het adres waar de schermen draaien; dat adres staat in de link.

Bied daarna een offerte aan met een tekenlink. Binnen een paar seconden staat het bericht in het postvak, en op de offerte staat dat er gemaild is. `deploy/local/mail.sh inbox` geeft het postvak als JSON.

Op het hostingplatform zet de dienst "E-mail versturen" de vijf `SMTP_`-instellingen, nadat een beheerder van het platform de aanvraag heeft goedgekeurd. Het afzenderadres ligt daar vast; de naam ernaast stel je in bij de dienst.

## Meldingen

Meldingen op het eigen apparaat staan uit tot de instantie een sleutelpaar heeft. `just push-key` maakt er een en print de regel voor `backend/.env` (dat bestand staat niet in git). Daarna versturen de worker en de server ermee. Uitproberen kan alleen met een build van de frontend, omdat de service worker niet onder de ontwikkelserver draait. De stappen staan in [meldingen.md](meldingen.md).

## Teksten laten opstellen zonder VLAM

Lokaal heeft niemand een sleutel voor VLAM. Staat het opdrachtregelprogramma `claude` op je computer en ben je daar ingelogd, dan kan grip dat gebruiken als ontwikkelmodel:

```
LLM_PROVIDER=claude_cli
```

`just preview` zet dit zelf aan als het programma is gevonden en er geen VLAM is ingesteld. Op de pagina "Vacatureformulier en taalmodel" staat welke aanbieder actief is, met een knop om de verbinding te testen.

- Het werkt alleen in lokale ontwikkeling (`DEV_NO_AUTH` aan, geen `PUBLIC_HOST`). Daarbuiten weigert grip te starten met deze instelling.
- Tekst die je laat opstellen gaat naar een dienst buiten de overheid. Gebruik alleen verzonnen gegevens.
- Een concept duurt ongeveer twintig seconden.
- Het model kies je met `CLAUDE_CLI_MODEL` (standaard `sonnet`), de wachttijd met `CLAUDE_CLI_TIMEOUT_SECONDS`.

Zie ADR 0035.

## Wat hiermee is aangetoond

- De images bouwen en een instantie draait achter nginx, met migraties bij het starten.
- De login werkt tegen een echte identiteitsprovider, van doorsturen tot uitloggen, voor een bekende en een onbekende persoon, op beide instanties.
- Een bericht van grip gaat via outway en inway van de ene instantie naar de andere, en de ontvanger herkent de afzender aan het peer-id.
- Grip haalt een node en de keten op bij Bouwmeester, en Bouwmeester haalt de opdrachten bij een node op bij grip, beide via outway en inway van FSC.
- Wies haalt opdrachten en open rollen op uit grip, grip leest collega's en vaardigheden uit Wies, en een aanstaande collega komt in Wies aan als voorstel.

Wat het niet aantoont: iets over het platform zelf. Hostnamen, TLS in de pod, het aantal componenten per project en het register voor de FSC-images blijven vragen voor het platformteam.

## Als het niet werkt

- **De API geeft een vreemd antwoord na een herstart van de backend.** nginx zoekt het adres van de backend een keer op, bij het starten. Start je alles met `just local-up`, dan start nginx mee opnieuw. Maak je alleen een backend opnieuw aan, maak dan ook `frontend-a` of `frontend-b` opnieuw aan; anders praat nginx met wat er nu op het oude adres staat, en dat kan de andere instantie zijn.
- **Bouwmeester meldt dat een grip-instantie geen antwoord geeft.** Kijk in `deploy/local/state/dev-link/grip-federation.log`. Meestal loopt het schema van de database achter op de code (`just migrate`), of voldoet een opdracht niet aan het contract.
- **Na inloggen ben je toch niet ingelogd.** Kijk in de log van de backend naar "is not HTTPS". De provider moet https zijn.
- **`CERTIFICATE_VERIFY_FAILED` in de log van de backend.** De bundel in `state/tls/` hoort bij een andere CA. `just local-nuke` en opnieuw starten.
- **De inway meldt `INVALID_CERTIFICATE`.** De groepscertificaten zijn van voor een wijziging in `fsc-pki.sh`. Maak ze opnieuw en gooi de FSC-databases weg.
- **Het bouwen blijft hangen op het ophalen van pakketten.** Het backend-image haalt geduldig en met weinig tegelijk op, maar een traag netwerk blijft traag. Opnieuw proberen gaat verder waar het bleef.
