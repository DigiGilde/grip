# Uitrollen op ZAD

Begin met een voorbeeldinstantie. Die bevat alleen verzonnen gegevens, kan niets naar buiten sturen en laat zien of het platform, de login en de adressen kloppen voordat er echt werk in grip staat. De echte instantie komt daarna, in een eigen project.

Dit document is een lijst om af te lopen. Bovenaan staat wat lokaal is bewezen; bij elke stap staat of ze lokaal is uitgevoerd of pas op het platform kan.

## Wat lokaal is bewezen

Op 9 oktober 2026 zijn een echte instantie en een voorbeeldinstantie gedraaid zoals het platform ze aanbiedt: de twee images, elk onderdeel op een eigen hostnaam achter een proxy met TLS, een lege database per instantie, een Keycloak als identiteitsprovider, en de worker als eigen container. De backend kreeg alleen wat het platform aanreikt (`PUBLIC_HOST` van het eigen onderdeel, de database, de waarden van Keycloak) en de instellingen uit stap 3. Een echte browser liep de stappen door. De opstelling was eenmalig en staat niet in de repo.

| Wat | Bewezen | Hoe |
|---|---|---|
| Adressen afleiden uit `PUBLIC_HOST` | ja | De backend kreeg `https://component-2-...` en stuurde de login, de mail en de URI's naar `https://component-1-...`. `FRONTEND_URL` en `BACKEND_URL` waren niet gezet. |
| Cookies bij twee hostnamen | ja | `grip_session` en `grip_csrf` horen alleen bij de hostnaam van de frontend, met `Secure` en `SameSite=Lax`; de sessie is `HttpOnly`. Op de hostnaam van de backend bestaat geen sessie. |
| CSRF vanaf de frontend | ja | Een wijziging zonder token geeft 403, met token 201. |
| Eerste beheerder via `BOOTSTRAP_BEHEERDER_EMAILS` | ja | Eerste login maakt de persoon met de functie beheerder. |
| Uitloggen via de provider | ja | De browser komt terug op de inlogpagina; een volgende login vraagt het wachtwoord opnieuw. |
| Sessie na een herstart van de backend | ja | Container herstart, pagina herladen: nog ingelogd. |
| Onbekende persoon | ja | "Je bent ingelogd bij SSO Rijk, maar je hebt geen toegang tot deze omgeving. Vraag de beheerder om je toe te voegen." In Activiteit: "Inloggen geweigerd", met het adres en de reden. |
| Persoon met een niet bevestigd adres | ja | Dezelfde zin; de reden in Activiteit is "Adres niet bevestigd door de provider". |
| Lege instantie tot leven brengen | ja | Afzender met het meegeleverde profiel, een persoon met schaal, tarievenkaarten voor twee jaren, het register van organisaties opgehaald en een opdrachtgever met de hand toegevoegd, een opdracht met een begrotingsregel, een offerte. De wijzigingen zijn gedaan met de sessie van de beheerder op de hostnaam van de frontend, niet door elk formulier aan te klikken. |
| Pdf van de offerte | ja | Rijkslogo en huisstijllettertype uit het image; het enige adres in het document is `INSTANCE_BASE_URI`. |
| Tekenen door een genodigde | ja | Tweede gebruiker van de provider, via de link uit de mail. |
| Opnieuw inloggen bij een besluit | ja | Keycloak vraagt het wachtwoord opnieuw, ook met een lopende sessie (`prompt=login`, `max_age=0`). In het bewijs ligt de aanmelding 0 seconden voor het besluit. |
| Bewijs controleren zonder grip | ja | `python -m grip.proof.verify` keurt de bundel goed en herkent de pdf byte voor byte; een bundel met een gewijzigde hash wordt afgekeurd. |
| Passkey bij twee hostnamen | ja | Vastgelegd met de virtuele authenticator van Chrome; de passkey is gebonden aan de hostnaam van de frontend. Gebruikt voor een interne goedkeuring; de controle van het bewijs bevestigt de passkey. |
| Voorbeeldinstantie vult zichzelf, één keer | ja | 15 personen en 6 opdrachten op een lege database; een herstart vult niet opnieuw. |
| Bezoeker van het voorbeeld | ja | Een adres op `EXAMPLE_VISITORS` komt binnen als voorbeeldpersoon, ziet de vaste melding en wisselt van persoon in het accountmenu. |
| Wie niet op de lijst staat | ja | "Dit is een voorbeeld van grip. Je adres staat niet op de lijst van bezoekers. Vraag wie je de link gaf om je toe te voegen." |
| Wat een bezoeker doet draagt de bezoeker | deels | De gebeurtenis legt het adres van de bezoeker vast naast de voorbeeldpersoon. Het scherm Activiteit toont alleen de voorbeeldpersoon. |
| Pdf in het voorbeeld | ja | "Voorbeeld, geen echt document", geen Rijkslogo en geen huisstijllettertype, ook als het platform de instellingen daarvoor aanreikt. |
| Terugzetten met de hand en 's nachts | ja | `python -m grip.core.example` in de container, en de worker op het ingestelde uur. De nachtelijke poging botste één keer met de takenlus en slaagde een minuut later vanzelf. |
| Verkeerde database | ja | Voorbeeld op de database van de echte instantie en omgekeerd: beide weigeren te starten met een Nederlandse zin. |
| Worker als eigen container | ja | Draait de takenlus, de maillus als mail is ingesteld en in een voorbeeld de nachtelijke terugzetting. Zonder instellingen meldt hij per lus dat die uit staat. |
| Mail met een tekenlink | ja | Via de worker naar een lokale mailvanger; de link wijst naar de hostnaam van de frontend. |
| `TRUSTED_PROXIES` en de limiet op inloggen | ja | Twee afnemers achter de proxy. Met het bereik van de proxy's ingesteld blokkeert de limiet van de een de ander niet, ook niet met een vervalste `X-Forwarded-For`. Zonder de instelling delen ze één limiet. |
| Eén adres met twee paden op de router van het platform | nee | Niet lokaal te doen: het gaat om de router van het platform. |
| De Keycloak van het platform met SSO Rijk erachter | nee | Niet lokaal te doen. Of SSO Rijk zelf opnieuw om het wachtwoord vraagt, blijkt pas daar. |
| Images ophalen uit het register | nee | Niet lokaal te doen. |

Wat hierbij stuk ging en is hersteld:

- Een uitgerolde instantie zonder `FEDERATION_SIGNING_KEY` legt geen enkel besluit vast. Wie tekent logt opnieuw in en leest daarna "Het besluit kon niet worden ondertekend door deze omgeving." De sleutel staat nu in stap 3 en de backend meldt het ontbreken bij de start.
- De eigen logregels van de toepassing (`OIDC login: ...`) kwamen niet in het logboek van de container. Dat is hersteld.
- Een login stond in Activiteit als "Aanmelding gewijzigd". Dat is nu "Ingelogd", "Inloggen geweigerd" of "Voorbeeldpersoon gekozen".
- In het voorbeeld stond "Lokale ontwikkelaar" tussen de voorbeeldpersonen. Die wordt in een voorbeeldinstantie niet meer aangemaakt.

## Twee soorten instantie

| | Een voorbeeldinstantie | Een echte instantie |
|---|---|---|
| Project op ZAD | een eigen project, nooit dat voor echt werk | een eigen project |
| Database | leeg bij de eerste start, vult zichzelf met het voorbeeld | leeg bij de eerste start, blijft leeg |
| Instelling | `INSTANCE_MODE=voorbeeld` | geen `INSTANCE_MODE` |
| Wie komt binnen | wie op `EXAMPLE_VISITORS` staat, als bezoeker | wie een beheerder heeft toegevoegd |
| Eerste beheerder | niet van toepassing; `BOOTSTRAP_BEHEERDER_EMAILS` is hier een startfout | `BOOTSTRAP_BEHEERDER_EMAILS` |
| Mail, meldingen, Wies | uit, ook als het platform ze aanreikt | naar keuze |
| Federatie | alleen met andere voorbeelden, in een eigen FSC-groep (`EXAMPLE_FSC_GROUP`, ADR 0054) | naar keuze, nooit met een voorbeeld |
| Rijkslogo op documenten | nooit | naar keuze |
| Elke nacht | terug naar de beginstand | niets |

De server dwingt de scheiding af. Een voorbeeldinstantie start niet op een database met personen. Een echte instantie start niet op een database die ooit als voorbeeld is gevuld. Een voorbeeldinstantie gooi je weg; ze wordt nooit de echte. Zie ADR 0050.

## 1. Voor je begint

1. De wijzigingen staan op `main`. De workflow `Build and deploy` bouwt en rolt alleen uit bij een push naar `main` of een tag `v*`.
2. De workflow `CI` is groen op die commit.
3. De twee images komen in `ghcr.io/digigilde/grip/backend` en `ghcr.io/digigilde/grip/frontend`, met het label `sha-<zeven tekens>`. Het platform moet ze kunnen ophalen. Een pakket dat de workflow voor het eerst publiceert, krijgt de zichtbaarheid van de repo en is hier dus openbaar; een pakket dat iemand vanaf de eigen machine pusht, is privé (zie stap 1 van [de voorbeeldgroep](#stappen)). Een ophaalgeheim voor het project is nog niet geprobeerd.

## 2. Het project op ZAD

Maak een project met één uitrol (`main`) en twee onderdelen. De workflow verwacht deze namen.

| Onderdeel | Image | Poort | Pad | Gezondheidscontrole |
|---|---|---|---|---|
| `component-1` | frontend | 8080 | `/` | HTTP `GET /` |
| `component-2` | backend | 8080 | `/api` | HTTP `GET /api/health/ready` |

**Eén adres, twee paden.** Zet beide onderdelen achter hetzelfde adres: `/` naar `component-1`, `/api` naar `component-2`, zonder het pad te herschrijven. De browser ziet dan één adres en de cookies horen bij dat adres alleen. Dit is de bedoelde opzet.

Niet lokaal te doen: of de router van het platform een pad per onderdeel kan geven, blijkt op het platform.

Kan dat op het gekozen domein niet, dan is er een tweede weg, en die is lokaal gedraaid: geef `component-1` `uses-components: [component-2]` en zet op de frontend `BACKEND_URL=http://main-component-2:8080`. De frontend geeft `/api/` dan zelf door. De browser gebruikt alleen het adres van de frontend. Geeft het platform elk onderdeel een eigen adres van de vorm `component-2-<rest>` of `component-2.<rest>`, dan leidt de backend het adres van de frontend zelf af uit `PUBLIC_HOST` en hoef je niets te zetten. Bij een andere vorm zet je op de backend `FRONTEND_URL` en `BACKEND_URL` op het adres van de frontend.

TLS is nodig: de cookies zijn `Secure` en een passkey werkt alleen op een beveiligd adres. Lokaal was daar een eigen certificaat voor nodig; op het platform regelt de ingress dat.

Diensten voor het project:

| Dienst | Voor | Reikt aan |
|---|---|---|
| PostgreSQL | `component-2` | `DATABASE_SERVER_HOST`, `DATABASE_SERVER_PORT`, `DATABASE_SERVER_USER`, `DATABASE_PASSWORD`, `DATABASE_DB` |
| Keycloak met SSO Rijk | `component-2` | `OIDC_URL`, `OIDC_REALM`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_DISCOVERY_URL` |
| Publiceren op het web | beide | `PUBLIC_HOST` |

Registreer bij de Keycloak-dienst als omleidadres: `<adres>/api/auth/callback`. Als adres na uitloggen: `<adres>`. Het adres is dat van de frontend. Lokaal uitgevoerd met een eigen Keycloak.

De backend migreert de database zelf bij elke start. Een tweede start doet niets.

## 3. Instellingen van de backend

Zet deze als omgevingsvariabelen van `component-2`. Wat het platform aanreikt staat hierboven en zet je niet zelf.

| Variabele | Waarde | Geheim |
|---|---|---|
| `SESSION_SECRET_KEY` | een willekeurige waarde van 48 tekens of meer; maak haar met `openssl rand -base64 48` en plak haar in het geheimveld van het platform | ja |
| `GRIP_PROCESS` | `all` (de toepassing en de worker in één container) | nee |
| `INSTANCE_NAME` | de naam in de balk, bijvoorbeeld `Voorbeeldgilde` | nee |
| `INSTANCE_KEY` | een korte sleutel in kleine letters, bijvoorbeeld `voorbeeld` | nee |
| `INSTANCE_BASE_URI` | het publieke adres zonder schuine streep aan het eind | nee |
| `ORGANISATION_NAME` | de organisatie zoals ze een offerte ondertekent | nee |
| `FEDERATION_SIGNING_KEY` | de sleutel waarmee de instantie besluiten ondertekent (ES256, PEM); zie hieronder | ja |
| `TRUSTED_PROXIES` | het adresbereik van de proxy's voor de backend; zie stap 6 | nee |
| `RETENTION_HOUR` | het uur waarop de worker eens per dag de bewaartermijnen uitvoert, in de zone van de instantie; standaard `4`, leeg zet het uit; op een voorbeeldinstantie niet hetzelfde uur als `EXAMPLE_RESET_HOUR`. De termijnen zelf stelt de beheerder in onder Beheer, Bewaartermijnen | nee |

Zonder `INSTANCE_NAME`, `INSTANCE_KEY` en `INSTANCE_BASE_URI` start de instantie wel, maar heet ze "Grip (lokaal)" en beginnen haar URI's met `http://localhost:8010`. Een URI die eenmaal is uitgegeven verandert niet meer, dus zet deze drie voor de eerste start.

**De sleutel van de instantie.** Zonder `FEDERATION_SIGNING_KEY` kan niemand akkoord geven, afwijzen of intern goedkeuren, ook niet in een voorbeeldinstantie. De naam komt van de federatie, maar elk bewijs van een besluit wordt ermee ondertekend. Maak de sleutel zelf en plak de uitvoer in het geheimveld van het platform; regeleinden mogen als `\n` worden geschreven.

```sh
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256
```

Bewaar de sleutel. Een bewijs dat ermee is ondertekend blijft controleerbaar zolang de publieke helft bekend is; vervang je de sleutel, zet dan de oude publieke sleutel in `FEDERATION_RETIRED_JWKS`. Elke instantie krijgt een eigen sleutel.

**Alleen voor een voorbeeldinstantie:**

| Variabele | Waarde |
|---|---|
| `INSTANCE_MODE` | `voorbeeld` |
| `EXAMPLE_VISITORS` | wie binnen mag: domeinen of hele adressen, met komma's, bijvoorbeeld `voorbeeld.example,iemand@elders.example`. Leeg is niemand. |
| `EXAMPLE_RESET_HOUR` | het uur waarop de instantie 's nachts terug naar de beginstand gaat; standaard `3`, leeg is nooit |

**Alleen voor een echte instantie:**

| Variabele | Waarde |
|---|---|
| `BOOTSTRAP_BEHEERDER_EMAILS` | het adres van de eerste beheerder, zoals SSO Rijk het aanlevert |
| `LETTERHEAD_LOGO_PATH` | `/app/huisstijl/rijkslogo.svg`, alleen als de organisatie het Rijkslogo mag voeren |
| `DOCUMENT_FONT_DIR` | `/app/huisstijl/fonts`, onder dezelfde voorwaarde |
| `LETTERHEAD_LINES` | de regels onder de naam in de briefkop, gescheiden door `\|` |

De voorwaarden voor het logo en het lettertype staan in het image in `/app/huisstijl/NOTICES.md`.

**Zet deze niet.** De instantie weigert ermee te starten zodra `PUBLIC_HOST` gezet is: `DEV_NO_AUTH`, `OIDC_DIAGNOSTICS`, `OIDC_ALLOW_INSECURE_HTTP`, `LLM_PROVIDER=claude_cli`. Laat `SESSION_COOKIE_DOMAIN` leeg: op een domein dat het platform met andere projecten deelt zou een cookie voor het bovenliggende domein de sessie aan elk ander project geven.

De frontend heeft bij één adres met twee paden geen instellingen nodig.

**Op de frontend (`component-1`):** zet `SECURITY_TXT_URL` op het adres van de security.txt van de organisatie die de instantie beheert (https). `/.well-known/security.txt` verwijst daar dan naar. Zonder die waarde antwoordt het adres 404. Een voorbeeldinstantie is een proefomgeving: zet daar `INSTANCE_MODE=voorbeeld` ook op de frontend. Die antwoordt dan met een eigen security.txt die zegt dat het geen productie is, geeft een `robots.txt` die zoekmachines weert en zet `X-Robots-Tag: noindex`; `SECURITY_TXT_URL` telt dan niet. Wat er verder voor de beveiliging geregeld moet zijn staat in [beveiliging.md](beveiliging.md).

## 4. De koppeling met GitHub

De workflow rolt uit zodra de variabele `ZAD_PROJECT_ID` bestaat. Voer deze regels zelf uit; de sleutel wordt gevraagd en komt in geen logboek.

```sh
gh secret set ZAD_API_KEY --repo DigiGilde/grip
gh variable set ZAD_PROJECT_ID --repo DigiGilde/grip --body "<project-id>"
gh variable set ZAD_DEPLOYMENT_NAME --repo DigiGilde/grip --body "main"
```

De workflow kent één project. Zolang de voorbeeldinstantie het doel is, wijst `ZAD_PROJECT_ID` naar dat project. Daar draait elke instantie in een eigen uitrol. `ZAD_DEPLOYMENTS` noemt die uitrollen als JSON-lijst; zonder die variabele rolt de workflow alleen naar `ZAD_DEPLOYMENT_NAME` uit. Een uitrol met FSC staat ook in `ZAD_FSC_DEPLOYMENTS`, met de sleutel van haar peer; de directory heeft de sleutel `dir` (zie [Hoe het project van de voorbeelden staat na de uitrol](#hoe-het-project-van-de-voorbeelden-staat-na-de-uitrol)):

```sh
gh variable set ZAD_DEPLOYMENTS --repo DigiGilde/grip --body '["gilde","programma"]'
gh variable set ZAD_FSC_DEPLOYMENTS --repo DigiGilde/grip --body '{"directory":"dir","gilde":"a","programma":"d"}'
```

De workflow rolt in elke uitrol van `ZAD_DEPLOYMENTS` de frontend (`component-1`) en de backend (`component-2`) uit, en in een uitrol met FSC ook de listener (`federation`). De listener is hetzelfde image als de backend en gebruikt het schema dat de backend migreert, dus ze gaan samen. De onderdelen van FSC (manager, controller, transactielog, inway, outway en de bootstrap; in de directory `dirmgr` en `dirui`) gaan alleen mee bij een push naar `main` die hun images of de workflow verandert: een nieuw image herstart het netwerk van de groep. Zet een uitrol pas in een van de twee lijsten als haar onderdelen bestaan en hun instellingen hebben. De eerste uitrol van een onderdeel voegt het toe aan de uitrol, met of zonder instellingen. De eerste keer staat onder [Stappen](#stappen). `ZAD_FSC_DEPLOYMENTS` is een JSON-object van uitrol naar peer (`dir`, `a`, `b` of `d`); is het iets anders, zoals een lijst, dan stopt de uitrol van grip en FSC met een melding daarover.

## 5. De eerste uitrol

1. Push naar `main`, of start de workflow opnieuw op de laatste commit.
2. Wacht tot `build` en `deploy` klaar zijn.
3. Lees het logboek van `component-2`. Een geslaagde start eindigt met `Application startup complete`. Een weigering staat er als één Nederlandse zin, bijvoorbeeld over een ontbrekende `OIDC_ISSUER` of een standaardwaarde van `SESSION_SECRET_KEY`. Staat er `FEDERATION_SIGNING_KEY is not set`, zet dan eerst de sleutel uit stap 3. Een voorbeeldinstantie meldt bij de eerste start `Example instance: the example data was loaded`.
4. Open het adres. Een voorbeeldinstantie toont op de inlogpagina "Voorbeeld: alle gegevens zijn verzonnen."
5. Log in.
   - Voorbeeldinstantie: je komt binnen als bezoeker en ziet "Je bekijkt het voorbeeld als ...". In het accountmenu kies je een andere voorbeeldpersoon.
   - Echte instantie: je komt binnen als beheerder en ziet een lege instantie.
6. Lukt het inloggen niet, zoek in het logboek de regel `OIDC login:`. Die zegt welke claims de provider stuurde, of het adres bevestigd is, welke vorm het subject heeft en hoe oud de aanmelding was. Er staan geen namen of adressen in.

## 6. Na de eerste uitrol

1. Controleer in het logboek van de backend dat de worker draait: `Starting the worker...` en daarna `Taken bijgewerkt`. Draait de worker als eigen container naast de backend, dan kan hij bij de allereerste start twee foutmeldingen geven over tabellen die nog niet bestaan; hij probeert het opnieuw zodra de backend de database heeft gemigreerd.
2. Zet `TRUSTED_PROXIES` op het adresbereik van alles wat tussen de bezoeker en de backend staat: de ingress van het platform en, als de frontend `/api/` doorgeeft, de pods van de frontend. In de praktijk is dat het adresbereik van de pods van het cluster; vraag het aan het platformteam. Zonder die instelling ziet de backend elke bezoeker als hetzelfde adres en delen alle bezoekers één limiet van dertig inlogpogingen per minuut. Lokaal gemeten: met het bereik ingesteld krijgt de ene afnemer na dertig pogingen een 429 en de andere een gewone doorverwijzing; zonder de instelling krijgt ook de andere een 429. Het bereik zelf is niet lokaal te bepalen. Zo controleer je het op het platform: vraag `/api/auth/login` 31 keer op vanaf één adres en daarna één keer vanaf een ander adres; dat tweede moet een 302 geven.
3. Vraag op het adres `/api/people` op zonder in te loggen. Het antwoord is 401, net als voor `/api/docs` en `/api/openapi.json`.
4. Echte instantie: voeg in Beheer een tweede beheerder toe. `BOOTSTRAP_BEHEERDER_EMAILS` mag daarna blijven staan; weghalen neemt de functie niet af.
5. Echte instantie: vul het afzenderprofiel, een tariefkaart en de eerste personen in voordat de eerste opdracht komt.
6. Twee replica's: de sessies staan in de database, dus dat werkt voor inloggen. De limiet op inlogpogingen telt per replica.

## 7. Wat nog niet meegaat

- **Mail.** De dienst voor mail op het platform vraagt goedkeuring van de beheerder van het platform. Tot die tijd verstuurt een echte instantie geen uitnodigingen om te tekenen; de link kopieer je uit het scherm.
- **Meldingen.** `PUSH_VAPID_PRIVATE_KEY` en de bijbehorende publieke sleutel zijn niet gezet.
- **Federatie, Wies en de corpuskoppeling.** Staan uit. Federatie vraagt een eigen poort (8090).
- **Een taalmodel.** Zonder `VLAM_*` of een andere aanbieder werken de schrijfhulpen niet.
- **Twee projecten uit één workflow.** De workflow rolt naar één project uit. Een echte instantie naast de voorbeeldinstantie vraagt een tweede uitrolstap of een tweede set variabelen.
- **Meeschuivende voorbeeldgegevens.** De voorbeeldgegevens hebben vaste jaren, 2025 tot en met 2028, en zijn geschreven voor oktober 2026. Ze verschuiven niet mee met de dag van vandaag. Nu al zichtbaar: de maanden vanaf maart 2026 staan open en taken zijn sinds februari te laat. Vanaf december 2026 is de offerte van de opdracht voor 2027 verlopen, en vanaf januari 2027 klopt het lopende jaar niet meer. Wat mee moet schuiven: het lopende jaar met de tarievenkaarten eromheen en de namen van de opdrachten, tot welke maand er is afgesloten, en de data van lopende zaken (vacatures, de openstaande offerte) als een aantal dagen voor vandaag. Dat is een herschrijving van de voorbeeldgegevens en hun tests, en is nog niet gedaan. Welke set een voorbeeldinstantie laadt, kies je met `SEED_DATASET`: `voorbeeld` (standaard) of `programma`.
- **De bezoeker in Activiteit.** De gebeurtenis legt vast welke bezoeker iets deed; het scherm toont alleen de voorbeeldpersoon.
- **Standaardteksten in het voorbeeld.** De afzender van het voorbeeld heeft geen ondertekenaar en geen standaardteksten; een nieuwe offerte in het voorbeeld meldt die als ontbrekend.
- **Een eigen domein.** Vraag je aan bij het platform. Zet daarna `INSTANCE_BASE_URI` niet om: uitgegeven URI's blijven wat ze waren.

## Wat een voorbeeldinstantie extra vraagt van het platform

Niets buiten een eigen project met een eigen database. Ze gebruikt dezelfde twee onderdelen en dezelfde login. Mail hoeft niet te worden aangevraagd. De worker moet draaien (`GRIP_PROCESS=all`), anders gaat ze 's nachts niet terug naar de beginstand.

## Startpagina: het ontwikkelportaal

Eén adres voor wie de voorbeelden wil zien: onder Demo een knop naar elke voorbeeldinstantie, met haar rol en een zin uitleg, en verder de documentatie, de besluiten en het personaboek, met zoeken over alles. Het portaal is geen onderdeel van grip en heeft geen backend, login of gegevens.

Het staat in het project van de voorbeeldinstantie, in een eigen uitrol `portaal`, en wordt bijgewerkt bij elke push naar `main` (`Build and deploy`, de stappen `build-ontwikkelportaal` en `deploy-ontwikkelportaal`). Een pull request krijgt geen eigen uitrol.

| Onderdeel | Image | Poort | Pad | Gezondheidscontrole |
|---|---|---|---|---|
| `ontwikkelportaal` | `ghcr.io/digigilde/grip/ontwikkelportaal` | 8080 | `/` | HTTP `GET /` |

Het image bouwt de site met de zoekindex in de bouwfase en controleert daar de links; het uiteindelijke image is nginx met alleen de uitkomst. Het draait als gewone gebruiker en schrijft alleen in `/tmp`. De beveiligingskop staat `'wasm-unsafe-eval'` toe, anders start zoeken niet, en verder geen script uit de pagina zelf. Het is een proefomgeving: `robots.txt` en de kop `X-Robots-Tag` houden het buiten zoekmachines, en `/.well-known/security.txt` zegt dat het geen productie is en verwijst voor meldingen naar de repository. De container schrijft dat bestand bij het starten, zodat `Expires` binnen een jaar blijft.

### Eenmalig

In het project van de voorbeeldinstantie, met de sleutel van dat project:

```sh
zadctl component add ontwikkelportaal --port 8080 --path / --service publish-on-web
zadctl service config set health-check --component ontwikkelportaal \
  --set scheme=http --set port=8080 --set liveness-path=/ --set readiness-path=/
zadctl env add -c ontwikkelportaal 'ONTWIKKELPORTAAL_INSTANCES=[...]'
```

De variabele `ZAD_PROJECT_ID` en het geheim `ZAD_API_KEY` uit stap 4 zijn genoeg; er komt niets bij. Het pakket `ontwikkelportaal` publiceert de workflow, dus het is openbaar zoals de repo; controleer het na de eerste bouw zoals in stap 1 van [de voorbeeldgroep](#stappen).

### Welke instanties erop staan

`ONTWIKKELPORTAAL_INSTANCES` is een JSON-lijst met per instantie `naam`, `url` en optioneel `rol` en `omschrijving`; de velden staan in [lokaal.md](lokaal.md#ontwikkelportaal). Een latere wijziging gaat met `zadctl env set` en geldt vanaf de volgende start van de container. Met de voorbeeldinstanties en het overzicht van de directory uit [Voorbeeldinstanties met federatie](#voorbeeldinstanties-met-federatie):

```json
[
  {"naam": "MOZa voorbeeld", "rol": "Programma",
   "omschrijving": "Geeft opdrachten aan DigiGilde voorbeeld en boekt kosten die een leverancier voor het programma doet.",
   "url": "https://component-1-programma-<project>.<basisdomein>/"},
  {"naam": "DigiGilde voorbeeld", "rol": "Opdrachtnemer",
   "omschrijving": "Maakt offertes, voert opdrachten uit, sluit maanden af en factureert. Wie op de lijst van bezoekers staat, kijkt mee als voorbeeldpersoon.",
   "url": "https://component-1-gilde-<project>.<basisdomein>/"},
  {"naam": "Directory", "rol": "FSC-groep grip-voorbeeld",
   "omschrijving": "Welke voorbeeldinstanties in de groep zitten en welke diensten ze elkaar aanbieden.",
   "url": "https://dirui-directory-<project>.<basisdomein>/"}
]
```

### Het adres

Het portaal staat op https://grip-voorbeeld.rijks.app/, het adres waar eerder de voorbeeldinstantie stond. Zonder die instelling krijgt het het standaardadres van het cluster, `ontwikkelportaal-portaal-<project>.<cluster>`. Het adres staat op de uitrol:

```sh
zadctl deployment create portaal --domain-format subdomain \
  --subdomain grip-voorbeeld --base-domain rijks.app
```

`zadctl project check-subdomain <naam> rijks.app` zegt vooraf of een naam vrij is; `rijks.app` is een domein van het cluster. De workflow laat de instellingen van het adres staan als hij een nieuw image uitrolt.

## Hoe het project van de voorbeelden staat na de uitrol

Zo staat het project sinds de [stappen](#stappen) van de voorbeeldgroep op 28 november 2026 zijn gedaan.

Het project `gv-ukr` heeft een uitrol per organisatie, een voor de directory van de voorbeeldgroep en een voor de startpagina. Een database hoort bij een uitrol; de voorbeelden mogen worden weggegooid en opnieuw opgebouwd.

| Uitrol | Wat | Adres |
|---|---|---|
| `portaal` | De startpagina (het ontwikkelportaal) | https://grip-voorbeeld.rijks.app/ |
| `directory` | De directory van de FSC-groep `grip-voorbeeld` (`dirmgr`) en haar overzicht (`dirui`) | `dirui-directory-gv-ukr.<cluster>` |
| `gilde` | DigiGilde voorbeeld, peer a, met FSC | `component-1-gilde-gv-ukr.<cluster>` |
| `programma` | MOZa voorbeeld, peer d, met FSC | `component-1-programma-gv-ukr.<cluster>` |

- **De workflow rolt grip uit naar `gilde` en `programma`** (`ZAD_DEPLOYMENTS`), met de listener in beide (`ZAD_FSC_DEPLOYMENTS`, dat ook de directory noemt), en de startpagina naar `portaal`. De onderdelen van FSC gaan alleen mee als hun images veranderen.
- **Wat per instantie verschilt, staat op het onderdeel in de uitrol**, niet op het onderdeel zelf: `BACKEND_URL` op `component-1` (`http://gilde-component-2:8080`), en `INSTANCE_NAME`, `INSTANCE_KEY`, `INSTANCE_BASE_URI` en `ORGANISATION_NAME` op `component-2`. Zo: `zadctl env add -c component-2 --deployment <uitrol> --env-file <bestand>`, of `env set` voor een naam die daar al staat. Wat voor alle voorbeelden gelijk is, zoals `INSTANCE_MODE` en `EXAMPLE_VISITORS`, staat op het onderdeel: MOZa voorbeeld laat dezelfde bezoekers binnen als DigiGilde voorbeeld.
- **Keycloak maakt per uitrol een eigen client** (`gv-ukr-gilde`, `gv-ukr-programma`) in de realm van het project, `gv-ukr-odcn-production`. Het adres van elke frontend staat in `additional_redirect_uris` van de dienst `keycloak` op projectniveau; `service config set` schrijft het hele document, dus geef de volledige lijst mee.
- **Elke instantie heeft een eigen sleutel** (`FEDERATION_SIGNING_KEY`), per uitrol op `component-2` en `federation`; de bijlage `instance-signing-key` hangt niet meer aan `component-2`.
- **DigiGilde voorbeeld heet ook zo in de instantie** (`INSTANCE_NAME`, met `INSTANCE_KEY` `digigilde-voorbeeld`), zoals op de startpagina en in de sjablonen.
- **De databasegebruiker van `gilde` en `programma` mag 50 verbindingen**, in plaats van de standaard 20: backend, listener, manager, controller en transactielog delen hem.

## Voorbeeldinstanties met federatie

Voorbeeldinstanties laten pas zien wat grip doet als ze met elkaar praten: een kostenpost bij de leverancier, een aanvraag die aankomt. Ze federeren in een eigen FSC-groep, `grip-voorbeeld`, met een eigen test-CA en een eigen directory, en alleen met elkaar (ADR 0054). De opzet volgt het FSC-testnet van MijnOverheid Zakelijk (`MinBZK/moza-fsc-testnet`). Alles staat in `deploy/zad/fsc/`. Wat over het platform vaststaat en waar dat vandaan komt, staat onder [Wat het platform doet](#wat-het-platform-doet).

Eerst DigiGilde voorbeeld en MOZa voorbeeld: daarmee is de kostenpost met een uitvoerder te zien. Het Ministerie van BZK voorbeeld komt er later bij als derde uitrol.

### Topologie

Eén project, dat van de voorbeeldinstantie, met per peer een eigen uitrol. Een uitrol krijgt een eigen database.

| Uitrol | Peer | Onderdelen |
|---|---|---|
| `directory` | de directory | `dirmgr` (manager in directorymodus), `dirui` (overzicht van de groep) |
| `gilde` | a, DigiGilde voorbeeld | `component-1` (frontend), `component-2` (backend, `GRIP_PROCESS=all`), `federation` (de listener, alleen voor de inway), `manager`, `controller`, `inway`, `outway`, `txlog`, `fscboot-a` (de bootstrap van de peer) |
| `programma` | d, MOZa voorbeeld | hetzelfde, met `fscboot-d` |
| `ministerie` | b, Ministerie van BZK voorbeeld (later) | hetzelfde, met `fscboot-b` |

Een uitrol met FSC kan niet frontend en `/api` op één adres zetten, zoals de vroegere uitrol `main` deed: passthrough kan alleen als een onderdeel een eigen host heeft. Daarom heeft elke instantie de domeinvorm `component-deployment-project`, en is de startpagina het vaste adres.

Een onderdeel bestaat één keer in het project en draait in elke uitrol waaraan het gekoppeld is. Nieuw in het project zijn er tien: `federation`, `manager`, `controller`, `inway`, `outway`, `txlog`, `dirmgr`, `dirui`, `fscboot-a` en `fscboot-d`. `component-1` en `component-2` bestaan al.

- **Adressen.** De uitrollen gebruiken de domeinvorm `component-deployment-project`, dus een hostnaam is `<onderdeel>-<uitrol>-<project>.<basisdomein>`. Binnen een uitrol bereikt een onderdeel een ander als `<uitrol>-<onderdeel>`. Tussen uitrollen laat het netwerkbeleid van het platform geen rechtstreeks verkeer toe; peers bereiken elkaar op hun publieke hostnaam, poort 443.
- **De frontend geeft `/api` door.** `component-1` zet `BACKEND_URL` op de backend in de eigen uitrol (`<k>-frontend.env`), zodat de browser één adres gebruikt.
- **Eén database per uitrol.** Backend, listener, manager, controller en transactielog delen hem. OpenFSC zet zijn tabellen in eigen schema's (`contracts`, `peers`, `controller`, `transactionlog`); alleen de tabel met uitgevoerde migraties zou botsen, en daarom geven de wrapper-images elk onderdeel een eigen naam daarvoor. Lokaal nagelopen met OpenFSC 2.8.0. De nachtelijke reset van grip leegt alleen de tabellen van grip. De databasegebruiker van een uitrol mag standaard 20 verbindingen; voor deze vijf onderdelen samen is dat te krap, zet 50 (zie [Stappen](#stappen)).
- **Het adres van de database is een alias.** Manager, controller en transactielog lezen hun database uit `STORAGE_POSTGRES_DSN`. Het platform vult `$DATABASE_*` alleen in een alias in; in een gewone instelling blijft de tekst staan zoals hij is. Een alias hoort bij een onderdeel en geldt in elke uitrol, met de database van die uitrol. Hij gebruikt de poort die het platform aanreikt (`$DATABASE_SERVER_PORT`) en `sslmode=require`: de gedeelde PostgreSQL biedt TLS aan maar dwingt het nog niet af, en het platform vraagt elke app om `require` voordat het dat wel doet (`features/postgresql-tls.md` in `RijksICTGilde/RIG-Cluster`). De aliassen van één uitrol komen samen in één geheim van haar database en moeten daarom gelijk zijn; ze staan zo in elk sjabloon.
- **Instellingen per uitrol, bijlagen per onderdeel.** Wat per instantie verschilt, staat op het onderdeel in die uitrol: `zadctl env add -c <onderdeel> --deployment <uitrol> --env-file <bestand>`. Een bootstrap is de uitzondering: hij hoort bij één peer en draait in één uitrol, dus zijn instellingen staan op het onderdeel zelf (`zadctl env add -c fscboot-<k> --env-file <bestand>`). Een bijlage kan niet per uitrol. Ze hoort bij een onderdeel, en elke uitrol die het onderdeel draait krijgt al zijn bijlagen; de API en `zadctl` kennen geen koppeling per uitrol. Daarom heeft elke peer eigen paden in de pod, `/etc/fsc/<k>/group/` en `/etc/fsc/<k>/internal/` (k is `a`, `b` of `d`, en `dir` voor de directory), en wijzen de `TLS_*`-instellingen van een uitrol naar die van de eigen peer. Een pod van `gilde` bevat zo ook de sleutels van `programma`. In deze besloten voorbeeldgroep is dat aanvaard (ADR 0054); in een groep voor echt werk niet.

| Onderdeel | Image | Publicatie | Bijlagen |
|---|---|---|---|
| `manager`, `dirmgr` | `fsc-manager` (wrapper) | `publish-on-web` met `tls=passthrough`, poort 8443 | groep en intern |
| `inway` | `federatedserviceconnectivity/inway` | `publish-on-web` met `tls=passthrough`, poort 8443 | groep en intern |
| `outway` | `federatedserviceconnectivity/outway` | niet gepubliceerd | groep en intern |
| `controller` | `fsc-controller` (wrapper) | niet gepubliceerd: het scherm heeft geen login | intern |
| `txlog` | `fsc-txlog` (wrapper) | niet gepubliceerd | intern |
| `fscboot-<k>` | `fsc-bootstrap` | niet gepubliceerd, geen poort; de diensten `attachments` en `health-check` (`scheme=none`) | intern: de CA en het beheercertificaat van de peer |
| `dirui` | `federatedserviceconnectivity/directory-ui` | gewoon, met het certificaat van het platform | groep |
| `component-1`, `component-2` | `frontend`, `backend` | gewoon | geen |
| `federation` | `backend` met `GRIP_PROCESS=federation` | niet gepubliceerd; alleen de inway bereikt poort 8090 | geen |

Het platform kent geen init-containers. Daarom draaien manager, controller en transactielog in een dun wrapper-image dat eerst `migrate up` doet en daarna `serve`. De bootstrap is een eigen image met `bootstrap.sh`, `curl` en `jq`. De workflow bouwt ze naast de andere images (`fsc-manager`, `fsc-controller`, `fsc-txlog`), en de bootstrap (`fsc-bootstrap`) in een eigen stap, zodat een fout daar de images en de uitrol van grip niet ophoudt. De andere onderdelen gebruiken de images van OpenFSC zoals ze worden geleverd, versie 2.8.0. De versie staat één keer in de workflow (`OPENFSC_VERSION`), naast de digests van de geleverde images; verander ze samen.

### Stappen

De eerste keer gaat in deze volgorde. Het image van de bootstrap bestaat pas na een push naar `main`, dus de merge komt eerst. Daarna krijgt elke uitrol een eigen venster: `zadctl config set rollout false` slaat elke wijziging op zonder haar uit te rollen, `zadctl project pending` laat zien wat wacht, `zadctl project refresh` rolt alles in één keer uit en `zadctl config set rollout true` sluit het venster. Zo start geen onderdeel met de helft van zijn instellingen en herstart `gilde` één keer. Van de merge tot en met stap 10 gaat er verder niets naar `main`: een push tijdens een venster faalt op wat nog wacht (zie [Wat op het platform bleek](#wat-op-het-platform-bleek)).

1. **Merge, en controleer dat het image van de bootstrap op te halen is.** Merge met `ZAD_DEPLOYMENTS` en `ZAD_FSC_DEPLOYMENTS` nog niet gezet en niets in `zadctl project pending`. De workflow bouwt dan alle images, ook `fsc-bootstrap`, en rolt grip uit zoals voorheen, naar `ZAD_DEPLOYMENT_NAME`; de onderdelen van FSC laat hij staan. Het label van die push, `sha-<merge>`, geldt hieronder voor elk image van grip en FSC; de images van OpenFSC zelf staan met hun digest in de workflow (`OPENFSC_INWAY`, `OPENFSC_OUTWAY`, `OPENFSC_DIRECTORY_UI`). Een pakket dat de workflow met `GITHUB_TOKEN` voor het eerst publiceert, krijgt de zichtbaarheid van de repo ("The package inherits the visibility and permissions model of the repository where the workflow is run", in de documentatie van GitHub over pakketten uit een workflow). Bij deze openbare repo was `fsc-bootstrap` daarom meteen openbaar. Een pakket dat iemand vanaf de eigen machine pusht, is wel privé. Controleer het: `curl -s -o /dev/null -w '%{http_code}' 'https://ghcr.io/token?scope=repository:digigilde/grip/fsc-bootstrap:pull'` geeft 200 voor een openbaar pakket en 403 voor een privé pakket. Is het privé, maak het dan in het scherm openbaar: op de pagina van de organisatie onder Packages, `fsc-bootstrap`, Package settings, Danger Zone, Change visibility, Public. De API van GitHub kan dat niet, en het is niet terug te draaien. Privé houden kan ook: de dienst `image-registries` (`zadctl registry add`) haalt het pakket op met een persoonlijk token met `read:packages`. Dat token verloopt op productie na 90 dagen en geldt voor elk image onder het pad dat je opgeeft.
2. **Certificaten.** `deploy/zad/fsc/pki.sh` met `BASE_DOMAIN`, `PROJECT` en de uitrol per peer (`DEPLOYMENT_DIR`, `DEPLOYMENT_A`, `DEPLOYMENT_B`, `DEPLOYMENT_D`; ook `DEPLOYMENT_B` als het ministerie nog niet meedoet). Het maakt de test-CA van de groep, per peer een interne CA, en per onderdeel in een uitrol een map onder `state/pki/upload/<uitrol>/<onderdeel>/` met de bijlagen; `MANIFEST.tsv` zegt welk bestand op welk pad in de pod hoort, onder `/etc/fsc/<k>/`. Een bijlage is ten hoogste 64 KB; het script controleert dat. De sleutel van de groeps-CA gaat nooit in de repo en niet mee naar het platform. Bewaren hoeft niet: de groep is een voorbeeld, en `pki.sh --fresh` maakt een nieuwe. Dan gaan alle bijlagen opnieuw en moeten de FSC-databases leeg, want de contracten zijn met de oude sleutels getekend.
3. **Instellingen invullen.** Per onderdeel en peer staat een sjabloon in `deploy/zad/fsc/env/`: `directory-manager.env`, `directory-ui.env` en per instantie (`a`, `b`, `d`) `-frontend` (voor `component-1`), `-grip` (voor `component-2`), `-federation`, `-manager`, `-controller`, `-inway`, `-outway`, `-txlog` en `-bootstrap` (voor `fscboot-<k>`). `just zad-fsc-env <uitrol>` vult ze in, met dezelfde zes variabelen als `pki.sh`, en schrijft per onderdeel `state/env/<uitrol>/<onderdeel>.env`, met het adres van de database in `<onderdeel>.alias`. Het stopt als er een plaatshouder overblijft of als een `TLS_*`-pad niet in `MANIFEST.tsv` staat, en drukt aan het eind de opdrachten voor `zadctl` af; `--dry-run` toont de bestanden alleen. Een gewone `envsubst` maakt ook `$DATABASE_*` leeg; wie het met de hand doet, geeft hem de lijst uit de kop van een sjabloon.

   Een uitrol die al draait heeft namen op zijn onderdelen staan, en `zadctl env add` weigert een bestand met zo'n naam in zijn geheel. Geef die namen dan mee: `--existing <onderdeel>=<NAAM>,<NAAM>` zet hun regels in `<onderdeel>.set.env`, voor `zadctl env set`, en de rest in `<onderdeel>.env`. De namen geeft `zadctl -o json env list -c <onderdeel> --deployment <uitrol> | jq -r 'keys | join(",")'`; de waarden geeft de API niet. Voor `gilde`:

   ```sh
   just zad-fsc-env gilde --existing component-2=INSTANCE_BASE_URI --existing component-1=BACKEND_URL
   ```

   De bootstrap van een peer draait in één uitrol. Zijn instellingen staan daarom op het onderdeel zelf, zonder `--deployment`: dan staan ze er al wanneer het onderdeel in zijn uitrol komt, ook als de workflow het daar neerzet.

   In `-grip.env` en `-federation.env` staan de instellingen van een voorbeeldinstantie met federatie: `INSTANCE_MODE=voorbeeld`, `EXAMPLE_FSC_GROUP=grip-voorbeeld`, `EXAMPLE_RESET_HOUR` (op alle instanties hetzelfde uur), `SEED_DATASET`, `INSTANCE_NAME`, `INSTANCE_KEY`, `INSTANCE_TOOI_URI`, `INSTANCE_BASE_URI`, `EXAMPLE_INSTANCE_URIS` (waar de andere staan; op alle instanties gelijk), `FEDERATION_INBOUND_ENABLED`, `FEDERATION_OUTBOUND_ENABLED` en `OUTWAY_URL`, en in `-grip.env` ook `ORGANISATION_NAME`. Een nieuwe instantie neemt over wat op `component-2` zelf staat, en daar staat wat `gilde` bij de eerste uitrol kreeg; daarom zet `-grip.env` alles wat per instantie verschilt op haar eigen laag, en krijgt ze bij de geheimen (stap 5 hieronder) een eigen `SESSION_SECRET_KEY`. `EXAMPLE_VISITORS` en `VLAM_*` neemt ze bewust over: de bezoekerslijst kan namen bevatten en staat één keer op `component-2`, voor alle voorbeelden. De listener heeft geen login, maar start alleen met authenticatie: `-federation.env` zet `OIDC_ISSUER` op de realm van het project (`https://keycloak.rijksapp.nl/realms/<project>-odcn-production`), en hij krijgt een eigen `SESSION_SECRET_KEY`. `BOOTSTRAP_BEHEERDER_EMAILS` blijft weg: dat is in een voorbeeld een startfout.
4. **Venster 1: wat de uitrollen delen, en de directory.** Een bijlage hoort bij een onderdeel en geldt in elke uitrol die het draait; een latere wijziging herstart het onderdeel overal. De bijlagen van alle uitrollen gaan er daarom nu op, voordat een uitrol de onderdelen draait. Voeg de onderdelen eenmalig toe aan het project, met hun poorten, publicatie en de dienst `postgresql-database` waar een database nodig is (backend, listener, manager, controller, transactielog); in `gv-ukr` bestaan ze al, op de bootstraps na. De manager en `dirmgr` krijgen drie poorten met 8443 vooraan (`--ports 8443 --ports 8444 --ports 8445`): de eerste is die van de publicatie. Een bootstrap heeft geen poort. Geef de onderdelen van OpenFSC een gezondheidscontrole op TCP-poort 8081, waar hun monitoring luistert, en de listener een op HTTP-poort 8090 met `/healthz`. Zonder die dienst controleert het platform de eerste poort, en dat geeft op een TLS-poort bij elke controle een foutregel in het logboek. Een bootstrap luistert nergens; `scheme=none` zet de controle daar uit.

   ```sh
   zadctl config set rollout false
   zadctl component add fscboot-a --service attachments
   zadctl component add fscboot-d --service attachments
   zadctl service assign health-check -c manager -c controller -c inway -c outway -c txlog \
     -c dirmgr -c dirui -c federation -c fscboot-a -c fscboot-d
   for c in manager controller inway outway txlog dirmgr dirui; do
     zadctl service config set health-check --component "$c" --set scheme=tcp --set port=8081
   done
   zadctl service config set health-check --component federation \
     --set scheme=http --set port=8090 --set liveness-path=/healthz --set readiness-path=/healthz
   for c in fscboot-a fscboot-d; do
     zadctl service config set health-check --component "$c" --set scheme=none
   done
   just zad-fsc-attachments directory
   just zad-fsc-attachments gilde
   just zad-fsc-attachments programma
   zadctl deployment create directory --domain-format component-deployment-project \
     -c dirmgr --image ghcr.io/digigilde/grip/fsc-manager:sha-<merge>
   zadctl deployment assign directory dirui --image <OPENFSC_DIRECTORY_UI>
   ```

   Dan de opdrachten die `just zad-fsc-env directory` afdrukte (`env add` voor `dirmgr` en `dirui`, de alias van `dirmgr`), en:

   ```sh
   zadctl project pending
   zadctl project refresh
   zadctl config set rollout true
   ```

   Daarna toont `zadctl logs directory -c dirmgr` `manager: running migrations` en `manager: starting`, zonder fout over de database of TLS, en antwoordt `https://dirui-directory-<project>.<basisdomein>/`.
5. **Geheimen.** Ze gaan via stdin en komen in geen bestand; gebruik er nooit `--dry-run` bij, want dat toont de waarde. Elke instantie krijgt een eigen `FEDERATION_SIGNING_KEY`, dezelfde op `component-2` en `federation` van haar uitrol: de listener geeft de publieke sleutel aan de andere instanties. Een bijlage kan dat niet: ze geldt in elke uitrol van het onderdeel en gaat bovendien voor een instelling met dezelfde naam. Daarom gaat de bijlage `instance-signing-key` in het venster van `gilde` van `component-2` af, voordat `programma` voor het eerst start; anders tekent ook `programma` met de sleutel van `gilde`. Daar is het scherm niet voor nodig: `zadctl attachment unassign instance-signing-key component-2` haalt alleen die koppeling weg (in de API een `PATCH` met `remove`), en de bijlage blijft in de catalogus tot `zadctl attachment delete instance-signing-key`. De oude sleutel is niet terug te lezen, dus `gilde` krijgt een nieuwe; tot de nachtelijke terugzetting keurt de controle de bewijzen in haar voorbeeld af, daarna zijn ze met de nieuwe ondertekend. Een waarde mag geen regeleinde bevatten, dus schrijf ze als `\n`; grip zet ze terug. De listener krijgt een eigen `SESSION_SECRET_KEY`, en `component-2` van een nieuwe instantie ook; zonder die regel neemt ze de waarde van `gilde` over.

   ```sh
   key="$(openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 \
     | jq -Rs '{FEDERATION_SIGNING_KEY: gsub("\n"; "\\n")}')"
   for c in component-2 federation; do
     printf '%s' "$key" | zadctl env add -c "$c" --deployment <uitrol> -f - --yes
   done
   unset key
   printf '{"SESSION_SECRET_KEY": "%s"}' "$(openssl rand -hex 32)" \
     | zadctl env add -c federation --deployment <uitrol> -f - --yes
   ```

   Voor een nieuwe instantie, zoals `programma`, daarbij:

   ```sh
   printf '{"SESSION_SECRET_KEY": "%s"}' "$(openssl rand -hex 32)" \
     | zadctl env add -c component-2 --deployment <uitrol> -f - --yes
   ```

6. **Venster 2: `gilde`.** De onderdelen van FSC komen erbij, de instellingen van `component-1` en `component-2` veranderen en de instantie krijgt haar eigen sleutel, in één keer. Een onderdeel gaat via de API niet meer uit een uitrol; wie dat terug wil, maakt de uitrol opnieuw, met een lege database. `gilde` gaat voor `programma`, zodat geen instantie ooit met de sleutel van een andere start.

   ```sh
   zadctl config set rollout false
   zadctl deployment assign gilde federation --image ghcr.io/digigilde/grip/backend:sha-<merge>
   zadctl deployment assign gilde manager --image ghcr.io/digigilde/grip/fsc-manager:sha-<merge>
   zadctl deployment assign gilde controller --image ghcr.io/digigilde/grip/fsc-controller:sha-<merge>
   zadctl deployment assign gilde txlog --image ghcr.io/digigilde/grip/fsc-txlog:sha-<merge>
   zadctl deployment assign gilde inway --image <OPENFSC_INWAY>
   zadctl deployment assign gilde outway --image <OPENFSC_OUTWAY>
   zadctl deployment assign gilde fscboot-a --image ghcr.io/digigilde/grip/fsc-bootstrap:sha-<merge>
   ```

   Dan de opdrachten die `just zad-fsc-env gilde --existing ...` afdrukte (`env add` en `env set`, en de aliassen van manager, controller en transactielog, die daarna ook voor `programma` gelden), `zadctl attachment unassign instance-signing-key component-2` en de geheimen uit stap 5 hierboven voor `gilde`, en:

   ```sh
   zadctl service config set postgresql-database --target deployment --deployment gilde --set connection-limit=50
   zadctl project pending
   zadctl project refresh
   zadctl config set rollout true
   ```

   Daarna geeft `/api/instance` de naam `DigiGilde voorbeeld` en hetzelfde `base_uri` als eerst, eindigt het logboek van `component-2` op `Application startup complete`, start de listener op poort 8090 en bereikt de manager de directory. `fscboot-a` registreert en publiceert de dienst en wacht dan op peer d.
7. **Venster 3: `programma`.** Elk onderdeel heeft zijn instellingen voordat het start: `component-2` vult het voorbeeld één keer, bij de eerste start, en legt dan zijn URI's vast.

   ```sh
   zadctl config set rollout false
   zadctl deployment create programma --domain-format component-deployment-project \
     -c component-2 --image ghcr.io/digigilde/grip/backend:sha-<merge>
   zadctl deployment assign programma component-1 --image ghcr.io/digigilde/grip/frontend:sha-<merge>
   zadctl deployment assign programma federation --image ghcr.io/digigilde/grip/backend:sha-<merge>
   zadctl deployment assign programma manager --image ghcr.io/digigilde/grip/fsc-manager:sha-<merge>
   zadctl deployment assign programma controller --image ghcr.io/digigilde/grip/fsc-controller:sha-<merge>
   zadctl deployment assign programma txlog --image ghcr.io/digigilde/grip/fsc-txlog:sha-<merge>
   zadctl deployment assign programma inway --image <OPENFSC_INWAY>
   zadctl deployment assign programma outway --image <OPENFSC_OUTWAY>
   zadctl deployment assign programma fscboot-d --image ghcr.io/digigilde/grip/fsc-bootstrap:sha-<merge>
   ```

   Dan de opdrachten `env add` die `just zad-fsc-env programma` afdrukte (de aliassen staan er sinds venster 2), de geheimen uit stap 5 hierboven voor `programma`, met de regel voor `component-2`, en:

   ```sh
   zadctl service config set postgresql-database --target deployment --deployment programma --set connection-limit=50
   zadctl service config set keycloak --set template=sso-only --set account-link=automatic \
     --set 'additional_redirect_uris[0]=https://component-1-gilde-<project>.<basisdomein>/*' \
     --set 'additional_redirect_uris[1]=https://component-1-programma-<project>.<basisdomein>/*'
   zadctl project pending
   zadctl project refresh
   zadctl config set rollout true
   ```

   Elke frontend is een eigen adres om na het inloggen naar terug te keren, dus het adres van `component-1` in elke uitrol staat in `additional_redirect_uris` van de dienst `keycloak`; anders weigert de login met "Invalid parameter: redirect_uri" (zie [Wat op het platform bleek](#wat-op-het-platform-bleek)). `service config set` schrijft het hele document: neem over wat `zadctl service config get keycloak` toont en voeg alleen het adres van `programma` toe. Daarna geeft `/api/instance` van `programma` de naam `MOZa voorbeeld` en haar eigen `base_uri`.
8. **De groep inrichten.** Dat doet elke peer zelf, vanuit zijn uitrol: alleen daar zijn de beheer-API's van manager en controller (poort 8444) bereikbaar. De bootstrap `fscboot-<k>` draait `deploy/zad/fsc/bootstrap.sh` in een lus. Hij registreert de dienst `grip-opdrachtverkeer` bij de eigen controller, publiceert die in de directory, vraagt een verbinding met de dienst van elke andere peer in `PEERS`, en stuurt opnieuw wat OpenFSC niet meer probeert te bezorgen. De managers van de peers tekenen een verbindingscontract zodra het binnenkomt (`AUTO_SIGN_GRANTS=serviceConnection` in `-manager.env`), dus geen peer hoeft bij een ander iets te accepteren. Is alles geldig, dan zet de bootstrap de andere peers met hun grant hash in zijn logboek, als tabel en als SQL, en kijkt hij elk uur opnieuw. Mislukken tien rondes op rij voordat het een keer lukte, dan stopt hij, zodat het platform het laat zien; ook een fout in een adres telt dan mee. `PEERS=a d` in `-bootstrap.env` laat het ministerie nog buiten. Op een werkplek toont `bootstrap.sh --dry-run` de aanroepen van één ronde.
9. **Het peerregister van grip.** Lees de rijen in het logboek van de bootstrap (`zadctl logs gilde -c fscboot-a` en `zadctl logs programma -c fscboot-d`). Voer per instantie de andere peers in onder Beheer > Koppelingen > Nieuwe koppeling, als beheerder, met de schakelaar Voorbeeldinstantie aan, en test de verbinding ("Verbinding in orde; 1 sleutel(s) ontvangen"); of draai de SQL in de databaseconsole. Begin bij DigiGilde voorbeeld. Zodra MOZa voorbeeld de koppeling heeft, verstuurt het meteen het verzoek voor de kostenpost, en een instantie die de afzender nog niet kent, antwoordt met 403 "Deze peer is niet bekend bij deze instantie". De outbox ziet 403 als definitief; de kostenpost staat dan op "Geweigerd door Voorbeeldgilde". Vraag hem in dat geval opnieuw aan met Wijzig gegevens en Vraag wijziging, zonder iets te veranderen. Het register blijft bij de nachtelijke reset staan.
10. **Controle en afronden.** Log in als bezoeker op MOZa voorbeeld. De kostenpost "Zaalhuur bijeenkomst ondernemers november" wacht op DigiGilde voorbeeld; binnen een minuut staat hij daar aangemaakt en leest het programma hem terug. Bij MOZa voorbeeld staat dan "Uitgevoerd door Voorbeeldgilde", met de verwachte factuur; bij DigiGilde voorbeeld staat hij onder Financieel > Kosten, 0% gedekt tot DigiGilde hem met een eigen begrotingsregel dekt. Zet dan de startpagina op de instanties en de directory (zie [Welke instanties erop staan](#welke-instanties-erop-staan); `ONTWIKKELPORTAAL_INSTANCES` staat op het onderdeel zelf, dus `zadctl env set -c ontwikkelportaal`), en als laatste `ZAD_DEPLOYMENTS` en `ZAD_FSC_DEPLOYMENTS` zoals in [De koppeling met GitHub](#4-de-koppeling-met-github). Daarmee eindigt de stop op `main`: de volgende push rolt grip en de listener naar beide instanties uit, en de onderdelen van FSC alleen als hun images veranderen.

### Wat het platform doet

Gelezen in de code van het platform (`RijksICTGilde/RIG-Cluster`), de API van `zadctl` en het FSC-testnet van MOZa op hetzelfde cluster, op 27 november 2026. De uitrol van 28 november bevestigde de hostnaam van een andere uitrol, de poorten, de alias, de bijlagen per onderdeel en de waarschuwing over de rechten van een sleutel.

- **Schema's.** De databasegebruiker van een uitrol is eigenaar van haar database en mag er schema's in maken; OpenFSC maakt `contracts`, `peers`, `controller` en `transactionlog`.
- **De publieke hostnaam van een andere uitrol.** Een pod bereikt de router van het cluster op poort 443, dus ook de manager en de inway van een andere uitrol in hetzelfde project. Rechtstreeks verkeer tussen uitrollen blijft dicht.
- **Meer poorten.** Met `--ports` luistert een onderdeel op meer poorten binnen de uitrol. De eerste is die van de publicatie en van de standaard gezondheidscontrole.
- **De beheer-API's.** Poort 8444 van manager en controller is van buiten niet te bereiken: het platform publiceert alleen de eerste poort, op 443, en kent geen exec of port-forward. Daarom richt elke peer zich in met een eigen bootstrap.
- **Bijlagen** horen bij een onderdeel, niet bij een uitrol (zie de topologie).
- **`$DATABASE_*`** vult het platform alleen in een alias in, niet in een gewone instelling.
- **Een sleutel als bijlage** krijgt geen rechten 0600: het platform zet die niet. OpenFSC meldt een waarschuwing die niets tegenhoudt.
- **Images van Docker Hub** haalt het cluster via een eigen proxy; de workflow noemt de geleverde images van OpenFSC met hun digest.

In de code van het platform is geen grens gevonden op het aantal onderdelen, uitrollen of databases per project.

### Een andere weg

In plaats van een eigen groep kunnen de voorbeelden aansluiten bij het testnet van MijnOverheid Zakelijk of bij de demogroep van OpenFSC. Dat scheelt de directory en de test-CA, maar vraagt hun akkoord, en de grens van ADR 0054 leunt dan alleen nog op het peerregister: `EXAMPLE_FSC_GROUP` is dan de id van die gedeelde groep.

## Wat eerder al was aangetoond

- De workflow `CI` loopt groen op een schone kopie: lint, de migraties op een lege PostgreSQL 16, de tests van de backend op Python 3.12 onder Linux, en lint, types, tests en bouwen van de frontend.
- Beide images bouwen voor `linux/amd64` met de argumenten van de workflow. De opstelling van 9 oktober draaide images die voor de eigen machine waren gebouwd.
- Het image van de backend, met `PUBLIC_HOST` gezet: weigert zonder login-instellingen en met de standaardwaarde van `SESSION_SECRET_KEY`; migreert een lege database en doet bij de tweede start niets; geeft zonder sessie alleen de gezondheidscontrole, de naam van de instantie en de inlogstatus; negeert het ontwikkelcookie.
- Het image van de frontend: start zonder `BACKEND_URL` en antwoordt dan op `/api/` met een duidelijke 502; de service worker en de startpagina worden nooit bewaard, de bestanden onder `/assets/` altijd.
- De voorbeeldmodus vult ook goed als twee replica's tegelijk starten.

## Wat op het platform bleek

De eerste uitrol, een voorbeeldinstantie, is gedaan op 9 oktober 2026 met `zadctl`. Wat daarbij bleek:

- **De images moeten op te halen zijn.** Een openbare repo maakt de pakketten niet openbaar; dat zet je per pakket bij de instellingen van het pakket. Na het openbaar maken was een extra uitrol nodig voordat de backend opkwam.
- **Een adres op een domein van het platform wacht op goedkeuring** van een platformbeheerder. Tot die tijd krijgt elk onderdeel een eigen clusteradres, `component-1-main-<project>.<cluster>` en `component-2-main-<project>.<cluster>`.
- **Op de clusteradressen** bereikt de browser alleen de frontend. Zet daar `BACKEND_URL=http://main-component-2:8080`; zonder poort loopt elk verzoek naar `/api/` vast. Onderdelen binnen één uitrol mogen elkaar bereiken; `uses-components` is niet nodig.
- **Op het goedgekeurde adres** staan beide onderdelen achter één adres: `/` naar `component-1`, `/api` naar `component-2`, zonder herschrijven. Geef de paden op bij het aanmaken van de onderdelen.
- **Keycloak kent alleen het adres van het onderdeel waaraan de dienst hangt** als terugkeeradres. Op de clusteradressen is dat de backend, terwijl grip via de frontend terugkeert: de login geeft dan "Invalid parameter: redirect_uri". Zet het adres van de frontend in `additional_redirect_uris` van de dienst.
- **De sleutel van de instantie** gaat als bijlage die het onderdeel als omgevingsvariabele krijgt (`FEDERATION_SIGNING_KEY`); regeleinden blijven dan heel. Dat past bij een project met één instantie. Draaien er meer in een project, dan krijgt elke uitrol een eigen sleutel als instelling, met `\n` voor de regeleinden: een bijlage geldt in elke uitrol van het onderdeel (zie [Voorbeeldinstanties met federatie](#voorbeeldinstanties-met-federatie)).
- **De gezondheidscontrole** staat per onderdeel als HTTP op poort 8080: `/` voor de frontend, `/api/health/live` en `/api/health/ready` voor de backend.
- **Een API-sleutel hoort bij een lid, niet bij een project** (zad-cli 0.14). `zadctl project use` geeft dan "No API key": maak een token op het tabblad Team van het project, onder Leden en tokens, en zet het als `ZAD_API_KEY` in `.env.zadctl`.
- **Opgeslagen maar niet uitgerolde wijzigingen laten de uitrol in de workflow falen.** Wie met `--no-rollout` werkt, rolt daarna zelf uit met `zadctl project refresh`; anders meldt de deploy-action "saved but not rolled out" en stopt de stap, ook als de nieuwe image wel draait.

De opdrachten, in volgorde, voor een nieuw project (de geheimen ontstaan in de opdracht zelf en komen in geen logboek):

```sh
zadctl project create "<naam>" --description "<waarvoor>"
zadctl config set rollout false
zadctl service config set postgresql-database --target project --set scope=shared
zadctl service config set keycloak --set template=sso-only --set account-link=automatic \
  --set 'additional_redirect_uris[0]=https://<adres>/*'
zadctl component add component-1 --port 8080 --path / --service publish-on-web
zadctl component add component-2 --port 8080 --path /api \
  --service publish-on-web --service postgresql-database --service keycloak
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 \
  | zadctl attachment assign instance-signing-key component-2 -f - \
      --provide-as env-var --env-name FEDERATION_SIGNING_KEY
zadctl env add -c component-2 --env-file <bestand met de instellingen uit stap 3>
zadctl service config set health-check --component component-1 \
  --set scheme=http --set port=8080 --set liveness-path=/ --set readiness-path=/
zadctl service config set health-check --component component-2 \
  --set scheme=http --set port=8080 --set liveness-path=/api/health/live --set readiness-path=/api/health/ready
zadctl deployment create main -f <manifest met beide onderdelen, het subdomein en het domein>
zadctl project refresh
```

De voorbeeldgroep met FSC is uitgerold op 27 en 28 november 2026, met de [stappen](#stappen) hierboven. Wat daarbij bleek:

- **De volgorde werkt.** Directory, `gilde` en `programma` gingen elk in een eigen venster zonder uitrol, in die volgorde.
- **De database met TLS werkt.** Manager, controller en transactielog migreren en starten via de alias, met `$DATABASE_SERVER_PORT` en `sslmode=require`.
- **Peers bereiken elkaar via de router.** De manager en de inway van een andere uitrol zijn op hun publieke hostnaam te bereiken, met passthrough en mTLS.
- **De eerste aanmelding bij de directory** gaf zo'n tien seconden lang EOF, tot de route klaar was. De bootstrap probeert het opnieuw.
- **De inway** kon zich bij de eerste start niet bij de controller registreren; even later lukte het vanzelf.
- **`fsc-bootstrap` was na de eerste push meteen openbaar** (zie stap 1).
- **`zadctl config set rollout false` geldt voor de map waar je staat.** Het schrijft de keuze in `.env.zadctl` in die map, als standaard voor `zadctl`; het platform kent geen instelling met die naam. Draai alle opdrachten van een venster in dezelfde map en zet de keuze daarna terug.
- **De bijlagen van een uitrol uploaden** duurt een paar minuten: voor `programma` waren het er 27.
- **`zadctl logs --tail` geeft ten hoogste 1000 regels.** Bij de backend vullen de gezondheidscontroles die in een paar uur; zoek met `--since` en filter ze weg.
- **De nachtelijke terugzetting** om 03:00 werkte in beide instanties, met de nieuwe namen en sleutels.
- **In stap 9 telt de volgorde.** MOZa voorbeeld kreeg zijn koppeling eerst en verstuurde het verzoek voor de kostenpost voordat DigiGilde voorbeeld MOZa kende; DigiGilde weigerde het. Opnieuw aangevraagd kwam het aan. Daarna gaf "Test de verbinding" in beide richtingen "Verbinding in orde".

## Wat nog niet is gebleken

- De login met SSO Rijk zelf: welke claims er komen, of het adres als bevestigd wordt doorgegeven, en of SSO Rijk bij een besluit opnieuw om het wachtwoord vraagt. De regel `OIDC login:` in het logboek laat de eerste twee zien.
- Het adresbereik voor `TRUSTED_PROXIES`.
