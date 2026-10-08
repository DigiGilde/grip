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

Dit pad is voorbereid maar niet uitgevoerd: daarvoor is het geheim nodig. Twee dingen kunnen dus nog tegenvallen. Grip laat alleen iemand binnen van wie de provider het e-mailadres als geverifieerd meldt; of deze realm dat doet voor adressen uit SSO Rijk is niet gecontroleerd. En of de client het terugkeeradres na uitloggen toestaat is ook niet gecontroleerd.

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

## Wat hiermee is aangetoond

- De images bouwen en een instantie draait achter nginx, met migraties bij het starten.
- De login werkt tegen een echte identiteitsprovider, van doorsturen tot uitloggen, voor een bekende en een onbekende persoon, op beide instanties.
- Een bericht van grip gaat via outway en inway van de ene instantie naar de andere, en de ontvanger herkent de afzender aan het peer-id.

Wat het niet aantoont: iets over het platform zelf. Hostnamen, TLS in de pod, het aantal componenten per project en het register voor de FSC-images blijven vragen voor het platformteam.

## Als het niet werkt

- **De API geeft een vreemd antwoord na een herstart van de backend.** nginx zoekt het adres van de backend een keer op, bij het starten. In deze omgeving start nginx daarom mee opnieuw; start je de backend met de hand, herstart dan ook `frontend-a`.
- **Na inloggen ben je toch niet ingelogd.** Kijk in de log van de backend naar "is not HTTPS". De provider moet https zijn.
- **`CERTIFICATE_VERIFY_FAILED` in de log van de backend.** De bundel in `state/tls/` hoort bij een andere CA. `just local-nuke` en opnieuw starten.
- **De inway meldt `INVALID_CERTIFICATE`.** De groepscertificaten zijn van voor een wijziging in `fsc-pki.sh`. Maak ze opnieuw en gooi de FSC-databases weg.
- **Het bouwen blijft hangen op het ophalen van pakketten.** Het backend-image haalt geduldig en met weinig tegelijk op, maar een traag netwerk blijft traag. Opnieuw proberen gaat verder waar het bleef.
