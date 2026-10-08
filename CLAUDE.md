# Werken in deze repo

Grip is een FastAPI-backend met een React-frontend. De achtergrond staat in `docs/`; dit bestand bevat alleen de regels.

## Taal

- Code, identifiers en commentaar in het Engels. `budget_line`, niet `begrotingsregel`.
- UI-teksten, foutmeldingen voor gebruikers en commits in het Nederlands.
- Domeintermen zonder goede Engelse vorm blijven Nederlands. De begrippenlijst in `docs/domein.md` bepaalt welke codenaam bij welke UI-term hoort.

## Gereedschap

- Python draait via `uv`, ook losse scripts.
- Taken staan in de `justfile`. Voeg een recept toe in plaats van een los shellscript.
- De frontend gebruikt `npm` en `@nldd/design-system`.

## Lagen in de backend

Onder `backend/grip/`:

| Map | Inhoud |
|---|---|
| `core` | Configuratie, app-opbouw, auth, de beslisfunctie |
| `middleware` | Sessie, CSRF, verplichte authenticatie |
| `api/routes` | HTTP-routes; dun, geen domeinlogica |
| `schema` | Pydantic-schema's voor verzoek en antwoord |
| `services` | Domeinlogica en statusovergangen |
| `repositories` | Databasetoegang |
| `models` | SQLAlchemy-modellen |
| `calc` | Rekenregels R1 t/m R14 |
| `migrations` | Alembic-migraties |

Een route roept een service aan, een service een repository. Sla geen laag over.

## Rekenen

- Rekenregels staan alleen in `backend/grip/calc`. Die module is puur: geen database, geen HTTP, geen klok.
- Implementeer een regel nooit opnieuw in een query, een view of de frontend. Roep de module aan.
- Geld is een geheel aantal centen. Gebruik nooit floating point voor bedragen.
- FTE en percentages zijn exacte decimalen.
- Rond pas af bij het tonen of vastleggen van een totaal.
- Afgeleide waarden (begroot op een personeelsregel, uitputting, beschikbaar, prognose, dekking) worden berekend en niet opgeslagen.
- Een uitgegeven offerte is een bevroren momentopname. Latere wijzigingen in tarieven of begroting veranderen haar niet.
- Elke regel heeft een unittest met het rekenvoorbeeld uit `docs/domein.md`.

## Toegang

- Elke toegangsbeslissing loopt via de ene functie `decide(subject, action, resource, data_class)`. Schrijf geen losse controles in routes of services.
- Elk veld hoort bij precies een gegevensklasse (A t/m F). Bouw antwoordschema's per klasse op, zodat een niet-toegestane klasse niet in het antwoord zit.
- Elke route heeft een autorisatie-afhankelijkheid. De inventaristest laat de build falen als die ontbreekt.
- Verberg nooit alleen iets in de UI. De server dwingt af.
- Voeg bij een nieuw veld een lektest toe op API-niveau.
- Sla geen salarisschaal op.

## De naad tussen de sporen

- Spoor A (uitvoering) weet niets van FSC. Het schrijft gebeurtenissen naar `federation_outbox`.
- Spoor B (federatie) raakt geen domeintabellen rechtstreeks. Het verstuurt uit de outbox en verwerkt inkomende berichten via de servicelaag van spoor A.
- De contracten voor `grip-opdrachtverkeer` en `corpus-context` staan in een aparte repo. Wijzig een contract daar, niet hier.

## Tests

- Schermtests worden met Playwright opgenomen door een persoon. Schrijf geen synthetische UI-interacties.
- Unittests voor de rekenmodule draaien zonder database.

## Besluiten

Leg een keuze die anderen bindt vast als ADR in `docs/adr/`, genummerd, met context, besluit en gevolgen.

## Publiceren

Schrijf geen namen van personen en geen lokale paden in code, documentatie, commits of issues. Verwijs naar andere systemen bij naam.
