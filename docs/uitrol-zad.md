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
| Mail, meldingen, federatie, Wies | uit, ook als het platform ze aanreikt | naar keuze |
| Rijkslogo op documenten | nooit | naar keuze |
| Elke nacht | terug naar de beginstand | niets |

De server dwingt de scheiding af. Een voorbeeldinstantie start niet op een database met personen. Een echte instantie start niet op een database die ooit als voorbeeld is gevuld. Een voorbeeldinstantie gooi je weg; ze wordt nooit de echte. Zie ADR 0050.

## 1. Voor je begint

1. De wijzigingen staan op `main`. De workflow `Build and deploy` bouwt en rolt alleen uit bij een push naar `main` of een tag `v*`.
2. De workflow `CI` is groen op die commit.
3. De twee images komen in `ghcr.io/digigilde/grip/backend` en `ghcr.io/digigilde/grip/frontend`, met het label `sha-<zeven tekens>`. Het platform moet ze kunnen ophalen: maak de twee pakketten openbaar of geef het project een ophaalgeheim. Dit is op het platform nog niet geprobeerd.

## 2. Het project op ZAD

Maak een project met één uitrol (`main`) en twee onderdelen. De workflow verwacht deze namen.

| Onderdeel | Image | Poort | Pad | Gezondheidscontrole |
|---|---|---|---|---|
| `component-1` | frontend | 8080 | `/` | HTTP `GET /` |
| `component-2` | backend | 8080 | `/api` | HTTP `GET /api/health/ready` |

**Eén adres, twee paden.** Zet beide onderdelen achter hetzelfde adres: `/` naar `component-1`, `/api` naar `component-2`, zonder het pad te herschrijven. De browser ziet dan één adres en de cookies horen bij dat adres alleen. Dit is de bedoelde opzet.

Niet lokaal te doen: of de router van het platform een pad per onderdeel kan geven, blijkt op het platform.

Kan dat op het gekozen domein niet, dan is er een tweede weg, en die is lokaal gedraaid: geef `component-1` `uses-components: [component-2]` en zet op de frontend `BACKEND_URL=http://main-component-2`. De frontend geeft `/api/` dan zelf door. De browser gebruikt alleen het adres van de frontend. Geeft het platform elk onderdeel een eigen adres van de vorm `component-2-<rest>` of `component-2.<rest>`, dan leidt de backend het adres van de frontend zelf af uit `PUBLIC_HOST` en hoef je niets te zetten. Bij een andere vorm zet je op de backend `FRONTEND_URL` en `BACKEND_URL` op het adres van de frontend.

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

## 4. De koppeling met GitHub

De workflow rolt uit zodra de variabele `ZAD_PROJECT_ID` bestaat. Voer deze regels zelf uit; de sleutel wordt gevraagd en komt in geen logboek.

```sh
gh secret set ZAD_API_KEY --repo DigiGilde/grip
gh variable set ZAD_PROJECT_ID --repo DigiGilde/grip --body "<project-id>"
gh variable set ZAD_DEPLOYMENT_NAME --repo DigiGilde/grip --body "main"
```

De workflow kent één project. Zolang de voorbeeldinstantie het doel is, wijst `ZAD_PROJECT_ID` naar dat project.

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
- **Meeschuivende voorbeeldgegevens.** De voorbeeldgegevens hebben vaste jaren, 2025 tot en met 2028, en zijn geschreven voor oktober 2026. Ze verschuiven niet mee met de dag van vandaag. Nu al zichtbaar: de maanden vanaf maart 2026 staan open en taken zijn sinds februari te laat. Vanaf december 2026 is de offerte van de opdracht voor 2027 verlopen, en vanaf januari 2027 klopt het lopende jaar niet meer. Wat mee moet schuiven: het lopende jaar met de tarievenkaarten eromheen en de namen van de opdrachten, tot welke maand er is afgesloten, en de data van lopende zaken (vacatures, de openstaande offerte) als een aantal dagen voor vandaag. Dat is een herschrijving van de voorbeeldgegevens en hun tests, en is nog niet gedaan.
- **Bewaartermijnen.** De worker past de bewaartermijnen niet toe. Dat is een losse taak, `python -m grip.events.retention` in de container van de backend; lokaal gedraaid, met de standaardtermijn (nooit) wist ze niets. Wie een termijn instelt in Beheer moet die taak zelf elke nacht laten draaien, bijvoorbeeld met een geplande taak van het platform.
- **De bezoeker in Activiteit.** De gebeurtenis legt vast welke bezoeker iets deed; het scherm toont alleen de voorbeeldpersoon.
- **Standaardteksten in het voorbeeld.** De afzender van het voorbeeld heeft geen ondertekenaar en geen standaardteksten; een nieuwe offerte in het voorbeeld meldt die als ontbrekend.
- **Een eigen domein.** Vraag je aan bij het platform. Zet daarna `INSTANCE_BASE_URI` niet om: uitgegeven URI's blijven wat ze waren.

## Wat een voorbeeldinstantie extra vraagt van het platform

Niets buiten een eigen project met een eigen database. Ze gebruikt dezelfde twee onderdelen en dezelfde login. Mail hoeft niet te worden aangevraagd. De worker moet draaien (`GRIP_PROCESS=all`), anders gaat ze 's nachts niet terug naar de beginstand.

## Wat eerder al was aangetoond

- De workflow `CI` loopt groen op een schone kopie: lint, de migraties op een lege PostgreSQL 16, de tests van de backend op Python 3.12 onder Linux, en lint, types, tests en bouwen van de frontend.
- Beide images bouwen voor `linux/amd64` met de argumenten van de workflow. De opstelling van 9 oktober draaide images die voor de eigen machine waren gebouwd.
- Het image van de backend, met `PUBLIC_HOST` gezet: weigert zonder login-instellingen en met de standaardwaarde van `SESSION_SECRET_KEY`; migreert een lege database en doet bij de tweede start niets; geeft zonder sessie alleen de gezondheidscontrole, de naam van de instantie en de inlogstatus; negeert het ontwikkelcookie.
- Het image van de frontend: start zonder `BACKEND_URL` en antwoordt dan op `/api/` met een duidelijke 502; de service worker en de startpagina worden nooit bewaard, de bestanden onder `/assets/` altijd.
- De voorbeeldmodus vult ook goed als twee replica's tegelijk starten.

## Wat pas op het platform blijkt

- De login via de Keycloak van het platform met SSO Rijk erachter: welke claims er komen, of het adres als bevestigd wordt doorgegeven, en of SSO Rijk bij een besluit zelf opnieuw om het wachtwoord vraagt. De regel `OIDC login:` in het logboek laat de eerste twee zien.
- Het pad `/api` op de router van het platform, en de vorm van het adres per onderdeel.
- Het ophalen van de images uit het register.
- Het adresbereik voor `TRUSTED_PROXIES`.
- Of het platform een geheim met regeleinden aanneemt (de sleutel van de instantie); anders schrijf je de regeleinden als `\n`.
