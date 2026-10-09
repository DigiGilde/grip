# Grip

Grip legt vast hoe een organisatie binnen de Rijksoverheid een opdracht uitvoert: de begroting, de offerte, wie erop werkt tegen welk tarief, externe kosten en hun dekking, de maandafsluiting en wat er gefactureerd moet worden. Het is bedoeld om een Grist-document te vervangen dat bij DigiGilde dezelfde naam draagt.

Elke organisatie of elk onderdeel draait een eigen instantie. Instanties wisselen aanvragen, offertes en akkoorden uit via FSC, en een opdracht verwijst met URI's naar de nodes in een beleidscorpus waar ze uit voortkomt.

## Waar het staat

Grip is in korte tijd gebouwd en is niet in productie. Lees het als een werkend geheel dat nog door mensen moet worden beproefd.

| | Stand |
|---|---|
| In gebruik | Nee. Er staan alleen fictieve voorbeeldgegevens in |
| Op het hostingplatform | Nee. Alles draait lokaal |
| Echte aanmelding via SSO Rijk | Nooit uitgevoerd. De aanmelding is aangetoond tegen een lokale Keycloak; er ligt een diagnose klaar voor de eerste echte aanmelding |
| Gegevens uit Grist | Niet geïmporteerd. De import is gebouwd en wacht op het document |
| Verkeer tussen twee instanties | Lokaal aangetoond, met FSC in een eigen testgroep |
| Context uit Bouwmeester | Lokaal aangetoond, met en zonder FSC, tegen een lokale Bouwmeester met fictieve nodes |
| Koppeling met Wies | Lokaal aangetoond, in beide richtingen |
| Mail en meldingen | Mail is aangetoond tegen een lokale mailvanger. Een melding is nooit via een echte meldingsdienst verstuurd |
| Taalmodel | VLAM is nooit aangeroepen. Lokaal neemt een ontwikkelmodel zijn plaats in |
| Tests | De backend- en frontendtests zijn groen. Schermen zijn daarnaast in een echte browser doorlopen; wat dat opleverde staat in [docs/rondgang.md](docs/rondgang.md) |

Wat op een beslissing of een antwoord wacht staat in [docs/openstaand.md](docs/openstaand.md). De stand per onderdeel staat in [docs/plan.md](docs/plan.md).

## Drie domeinen

| Domein | Vraag | Systeem |
|---|---|---|
| Corpus | Waarom doen we dit? | Bouwmeester: nodes en edges van politieke input tot instrument |
| Opdrachtverkeer | Wat is er tussen twee organisaties afgesproken? | Het koppelvlak tussen grip-instanties |
| Uitvoering | Hoe voeren we het uit? | Grip |

Een opdracht werkt volledig binnen een instantie. Het verkeer met een andere instantie is een laag erbovenop, zodat interne opdrachten en opdrachtgevers zonder grip ook passen.

## Lokaal starten

Je hebt Docker en `just` nodig. Voor werk buiten de containers ook `uv` en `npm`.

```
just dev      # database, backend en frontend, in de voorgrond
just seed     # fictieve voorbeeldgegevens in een lege database
```

Open daarna http://localhost:5183. Er is lokaal geen login: je bent de eerste beheerder uit de voorbeeldgegevens. Rechtsboven, onder je naam, kies je met "Bekijk als" een andere persoon.

| Service | Poort |
|---|---|
| Postgres | 5434 |
| Backend | 8010 |
| Frontend | 5183 |

Veelgebruikte recepten (`just` zonder iets toont ze allemaal):

| Recept | Doet |
|---|---|
| `just up`, `just down` | Start en stopt de services in de achtergrond |
| `just db` | Alleen de database, genoeg voor tests en migraties vanaf de eigen machine |
| `just migrate` | Voert de databasemigraties uit |
| `just test` | Draait de tests van backend en frontend (de backend heeft de database nodig) |
| `just lint`, `just typecheck` | Controleert stijl en types |
| `just preview` | De backend met de voorbeeldgegevens als Rijksorganisatie: documenten krijgen het Rijkslint, en het lokale ontwikkelmodel staat aan als het gevonden wordt |
| `just local-up` | De omgeving zoals die op het platform draait, op eigen poorten; zie [docs/lokaal.md](docs/lokaal.md) |
| `just check-spacing`, `just check-access` | Meet elk scherm in een browser: tussenruimte, en wat elke soort lezer ziet en mag |

Lokaal draait grip zonder identiteitsprovider. Dat is een bewuste keuze die `DEV_NO_AUTH` heet; zonder die instelling en zonder provider start grip niet.

## De code

| Map | Inhoud |
|---|---|
| `backend/grip/core` | Configuratie, de opbouw van de applicatie, aanmelden, de klok |
| `backend/grip/access` | De beslisfunctie en de gegevensklassen |
| `backend/grip/api/routes`, `schema` | De HTTP-routes en hun verzoeken en antwoorden |
| `backend/grip/services` | Domeinlogica en statusovergangen |
| `backend/grip/calc` | De rekenregels R1 t/m R14, zonder database of klok |
| `backend/grip/events` | De stroom van gebeurtenissen, de geschiedenis en "wat is er gebeurd" |
| `backend/grip/tasks` | Feiten, taken, het plan en het verloop van een zaak |
| `backend/grip/proof` | Het bewijs van een besluit en de controle daarvan |
| `backend/grip/federation` | Het verkeer met andere instanties en met een corpus |
| `backend/grip/integrations` | Wies, mail, meldingen, het register van organisaties |
| `backend/grip/data` | Meegeleverde gegevens: het plan en de teksten van taken, standaardteksten, het profiel van een organisatie |
| `backend/grip/migrations` | De databasemigraties |
| `frontend/src/ui` | De gedeelde bouwstenen van een scherm |
| `frontend/src/layout`, `routes.ts` | De schil, de hoofdbalk en welke pagina's er zijn |
| `frontend/src/features` | Een map per onderdeel van de applicatie |
| `deploy/local` | De lokale omgeving: images, Keycloak, FSC, mail |
| `docs` | De documentatie; begin bij [docs/README.md](docs/README.md) |

Het koppelvlak tussen instanties en met een corpus staat in een eigen repo; grip draagt een kopie mee die `just sync-contract` ververst.

## Documentatie

Begin bij [docs/README.md](docs/README.md): daar staat per soort lezer waar je begint. Wie in de repo werkt leest eerst [CLAUDE.md](CLAUDE.md).
