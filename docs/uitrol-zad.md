# Uitrollen op ZAD

Begin met een voorbeeldinstantie. Die bevat alleen verzonnen gegevens, kan niets naar buiten sturen en laat zien of het platform, de login en de adressen kloppen voordat er echt werk in grip staat. De echte instantie komt daarna, in een eigen project.

Dit document is een lijst om af te lopen. Achteraan staat wat lokaal is aangetoond en wat pas op het platform blijkt.

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

Kan dat op het gekozen domein niet, dan is er een tweede weg: publiceer alleen `component-1`, geef het `uses-components: [component-2]` en zet op de frontend `BACKEND_URL=http://main-component-2`. De frontend geeft `/api/` dan zelf door. Zet in dat geval op de backend `FRONTEND_URL` en `BACKEND_URL` op het adres van de frontend.

Diensten voor het project:

| Dienst | Voor | Reikt aan |
|---|---|---|
| PostgreSQL | `component-2` | `DATABASE_SERVER_HOST`, `DATABASE_SERVER_PORT`, `DATABASE_SERVER_USER`, `DATABASE_PASSWORD`, `DATABASE_DB` |
| Keycloak met SSO Rijk | `component-2` | `OIDC_URL`, `OIDC_REALM`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_DISCOVERY_URL` |
| Publiceren op het web | beide | `PUBLIC_HOST` |

Registreer bij de Keycloak-dienst als omleidadres: `<adres>/api/auth/callback`. Als adres na uitloggen: `<adres>`.

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

Zonder `INSTANCE_NAME`, `INSTANCE_KEY` en `INSTANCE_BASE_URI` start de instantie wel, maar heet ze "Grip (lokaal)" en beginnen haar URI's met `http://localhost:8010`. Een URI die eenmaal is uitgegeven verandert niet meer, dus zet deze drie voor de eerste start.

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
3. Lees het logboek van `component-2`. Een geslaagde start eindigt met `Application startup complete`. Een weigering staat er als één Nederlandse zin, bijvoorbeeld over een ontbrekende `OIDC_ISSUER` of een standaardwaarde van `SESSION_SECRET_KEY`.
4. Open het adres. Een voorbeeldinstantie toont op de inlogpagina "Voorbeeld: alle gegevens zijn verzonnen."
5. Log in.
   - Voorbeeldinstantie: je komt binnen als bezoeker en ziet "Je bekijkt het voorbeeld als ...". In het accountmenu kies je een andere voorbeeldpersoon.
   - Echte instantie: je komt binnen als beheerder en ziet een lege instantie.
6. Lukt het inloggen niet, zoek in het logboek de regel `OIDC login:`. Die zegt welke claims de provider stuurde, of het adres bevestigd is, welke vorm het subject heeft en hoe oud de aanmelding was. Er staan geen namen of adressen in.

## 6. Na de eerste uitrol

1. Controleer in het logboek van de backend dat de worker draait: `Starting the worker...` en daarna `Taken bijgewerkt`.
2. Zet `TRUSTED_PROXIES` op het adresbereik van de ingress van het platform. Zonder die instelling ziet de backend elke bezoeker als hetzelfde adres en delen alle bezoekers één limiet van dertig inlogpogingen per minuut.
3. Vraag op het adres `/api/people` op zonder in te loggen. Het antwoord is 401. `/docs` en `/openapi.json` geven 404.
4. Echte instantie: voeg in Beheer een tweede beheerder toe. `BOOTSTRAP_BEHEERDER_EMAILS` mag daarna blijven staan; weghalen neemt de functie niet af.
5. Echte instantie: vul het afzenderprofiel, een tariefkaart en de eerste personen in voordat de eerste opdracht komt.
6. Twee replica's: de sessies staan in de database, dus dat werkt voor inloggen. De limiet op inlogpogingen telt per replica.

## 7. Wat nog niet meegaat

- **Mail.** De dienst voor mail op het platform vraagt goedkeuring van de beheerder van het platform. Tot die tijd verstuurt een echte instantie geen uitnodigingen om te tekenen; de link kopieer je uit het scherm.
- **Meldingen.** `PUSH_VAPID_PRIVATE_KEY` en de bijbehorende publieke sleutel zijn niet gezet.
- **Federatie, Wies en de corpuskoppeling.** Staan uit. Federatie vraagt `FEDERATION_SIGNING_KEY` en een eigen poort (8090).
- **Een taalmodel.** Zonder `VLAM_*` of een andere aanbieder werken de schrijfhulpen niet.
- **Twee projecten uit één workflow.** De workflow rolt naar één project uit. Een echte instantie naast de voorbeeldinstantie vraagt een tweede uitrolstap of een tweede set variabelen.
- **Meeschuivende voorbeeldgegevens.** De voorbeeldgegevens hebben vaste jaren, 2025 tot en met 2028. Ze verschuiven niet mee met de dag van vandaag.
- **Een eigen domein.** Vraag je aan bij het platform. Zet daarna `INSTANCE_BASE_URI` niet om: uitgegeven URI's blijven wat ze waren.

## Wat een voorbeeldinstantie extra vraagt van het platform

Niets buiten een eigen project met een eigen database. Ze gebruikt dezelfde twee onderdelen en dezelfde login. Mail hoeft niet te worden aangevraagd. De worker moet draaien (`GRIP_PROCESS=all`), anders gaat ze 's nachts niet terug naar de beginstand.

## Wat is aangetoond en wat niet

Aangetoond, lokaal:

- De workflow `CI` loopt groen op een schone kopie: lint, de migraties op een lege PostgreSQL 16, de tests van de backend op Python 3.12 onder Linux, en lint, types, tests en bouwen van de frontend.
- Beide images bouwen voor `linux/amd64` met de argumenten van de workflow.
- Het image van de backend, met `PUBLIC_HOST` gezet: weigert zonder login-instellingen en met de standaardwaarde van `SESSION_SECRET_KEY`; migreert een lege database en doet bij de tweede start niets; maakt alleen de eerste beheerder aan; geeft zonder sessie alleen de gezondheidscontrole, de naam van de instantie en de inlogstatus; negeert het ontwikkelcookie; draait de worker stil als er niets is ingesteld.
- Het image van de frontend: start zonder `BACKEND_URL` en antwoordt dan op `/api/` met een duidelijke 502; geeft met `BACKEND_URL` door naar de backend; de service worker en de startpagina worden nooit bewaard, de bestanden onder `/assets/` altijd.
- Een offerte als pdf uit het image van de backend: met het Rijkslogo en het huisstijllettertype in een echte instantie, zonder beide en met "Voorbeeld, geen echt document" in een voorbeeldinstantie.
- De voorbeeldmodus: vullen op een lege database, ook als twee replica's tegelijk starten; weigeren in beide richtingen; terugzetten; de bezoeker met een nagebootste identiteitsprovider.

Nog niet aangetoond; let hierop bij de eerste uitrol:

- De login via de Keycloak van het platform, ook die van een bezoeker van een voorbeeldinstantie. Lokaal is de bezoeker alleen met een nagebootste provider geprobeerd.
- Het pad `/api` op de router van het platform en het ophalen van de images uit het register.
- Een adres per onderdeel (`component-1` en `component-2` elk een eigen adres). De afleiding van de adressen is getest; de opzet zelf is niet gedraaid. Gebruik één adres met twee paden.
