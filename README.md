# Grip

Grip legt vast hoe een organisatie binnen de Rijksoverheid een opdracht uitvoert: de begroting, wie erop werkt tegen welk tarief, externe kosten en hun dekking, de offerte en de maandelijkse verrekening. Het vervangt een Grist-document dat bij DigiGilde dezelfde naam draagt.

Elke organisatie of elk onderdeel draait een eigen instantie. Instanties wisselen aanvragen, offertes en akkoorden uit via FSC, en een opdracht verwijst met URI's naar de nodes in een beleidscorpus waar ze uit voortkomt.

## Drie domeinen

| Domein | Vraag | Systeem |
|---|---|---|
| Corpus | Waarom doen we dit? | Bouwmeester: nodes en edges van politieke input tot instrument |
| Opdrachtverkeer | Wat is er tussen twee organisaties afgesproken? | Het koppelvlak tussen grip-instanties |
| Uitvoering | Hoe voeren we het uit? | Grip |

Een opdracht werkt volledig binnen een instantie. Het verkeer met een andere instantie is een laag erbovenop, zodat interne opdrachten en opdrachtgevers zonder grip ook passen.

## Lokaal draaien

De backend staat in `backend/` en gebruikt `uv`. De frontend staat in `frontend/` en gebruikt `npm`. Alle taken lopen via `just`.

| Recept | Doet |
|---|---|
| `just up` | Start de services in containers |
| `just dev` | Start backend en frontend voor ontwikkeling |
| `just migrate` | Voert de databasemigraties uit |
| `just migration NAME` | Maakt een nieuwe migratie aan |
| `just test` | Draait de tests |
| `just lint` | Controleert de codestijl |
| `just typecheck` | Controleert de types |

Lokale poorten:

| Service | Poort |
|---|---|
| Postgres | 5434 |
| Backend | 8010 |
| Frontend | 5183 |

Lokaal draait grip zonder OIDC. Zet daarvoor `DEV_NO_AUTH`; inloggen via SSO Rijk is dan niet nodig.

## Documentatie

- [docs/architectuur.md](docs/architectuur.md): domeinen, identiteit, opdrachtverkeer, context uit het corpus, tekenen.
- [docs/domein.md](docs/domein.md): begrippen, datamodel, rekenregels R1 t/m R14, migratie vanuit Grist.
- [docs/toegang.md](docs/toegang.md): functies, relaties, gegevensklassen en de toegangsmatrix.
- [docs/plan.md](docs/plan.md): de twee bouwsporen, de eerste mijlpaal, risico's.
- [docs/adr/](docs/adr/README.md): de genomen besluiten, een per bestand.

Wie in de repo werkt leest eerst [CLAUDE.md](CLAUDE.md).
