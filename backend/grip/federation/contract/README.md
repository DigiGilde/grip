# Koppelvlakken

De contracten voor het verkeer tussen grip-instanties en corpus-systemen. Deze map is de bron
van waarheid: een implementatie volgt het contract, niet andersom.

| Dienst | Wie biedt hem aan | Contract |
|---|---|---|
| `corpus-context` | Elk corpus-systeem (Bouwmeester is de eerste implementatie) | `corpus-context/v1/openapi.yaml` |
| `grip-opdrachtverkeer` | Elke grip-instantie | `opdrachtverkeer/v1/openapi.yaml` |

Status: `1.0.0-alpha.1`. Nog niet vastgesteld; zie "Open punten".

## Wat staat waar

| Pad | Inhoud |
|---|---|
| `corpus-context/v1/`, `opdrachtverkeer/v1/` | OpenAPI 3.1 per dienst |
| `schemas/` | JSON Schema 2020-12, een bestand per object. De OpenAPI-documenten verwijzen ernaar, dus er is een definitie |
| `vocabulaire/` | Kernlijst van node-typen en edge-typen met URI's, en de regel voor eigen typen |
| `context.jsonld` | JSON-LD-context voor de termen uit de schema's en de woordenlijst |
| `examples/valid/`, `examples/invalid/` | Voorbeelden met fictieve gegevens; `<schema>[.<variant>].json` |
| `docs/conformance.md` | Hoe een implementatie aantoont dat ze voldoet |
| `spectral/` | De regels van de NL GOV API Design Rules, vastgelegd in de repo |

## Gebruik

```
just install    # eenmalig
just check      # lint, voorbeelden valideren, leespagina's bouwen
just build      # woordenlijst en JSON-LD-context opnieuw genereren
```

`just docs` schrijft naar `dist/`: een leespagina per dienst, een index met de woordenlijst, en
per dienst een gebundeld `openapi.json`. Dat laatste is de vorm die een implementatie serveert op
`/v1/openapi.json`.

## Afspraken in het contract

- **Namen.** De interface is Nederlands, zoals de NL GOV API Design Rules vragen: paden,
  schemanamen, velden en de waarden van codelijsten (statussen, vormen, soorten) volgen de
  begrippen van het domein: opdracht, opdrachtaanvraag, offerte, akkoord, afwijzing, voortgang,
  uitputting, factuurgegevens, eindrapport, vacature, aanbod, kostenpost, factuurregel,
  doorgifte, begrotingsregel, bemensing, capaciteit, corpus, woordenlijst, nodes, keten.
- **Wat niet vertaald is.** Termen uit standaarden en technische termen blijven zoals ze zijn:
  `id`, `uri`, `type`, `status` als veldnaam, `jws`, `kid`, `jwks`, `sha256`, de leden van een
  probleembericht (RFC 9457), de parameters voor paginering (`page`, `pageSize`), headernamen en
  de `x-`-uitbreidingen met hun waarden. Een `operationId` is de naam van de operatie in code en
  blijft Engels.
- **Vertaling naar code.** Een implementatie mag intern andere namen voeren. De vertaling zit
  dan op een plek, aan de grens. De tabel in `docs/termen.md` geeft bij elke term van het
  contract de codenaam die grip gebruikt.
- **Velden** in snake_case, query-parameters in camelCase, paden in kebab-case.
- **Identiteit.** Alles wat over de grens gaat heeft een URI van de instantie die het aanmaakt:
  `{corpus}/id/node/{uuid}`, `{basis}/id/opdracht/{uuid}`. Organisaties gaan op TOOI-URI.
- **Meerdere corpora.** Overal waar een node-URI staat, mag die uit een ander corpus komen. Een
  opdracht mag naar nodes uit meerdere corpora verwijzen.
- **Geld** in hele centen. FTE en percentages als decimale tekst. Geen floating point.
- **Datums** als `date`, tijdstippen als `date-time` met tijdzone.
- **Fouten** als `application/problem+json` (RFC 9457).
- **Idempotentie.** Elk gepusht bericht heeft een `id` (UUID). Eerste ontvangst: 201 met een
  ontvangstbevestiging. Hetzelfde `id` met dezelfde inhoud: 200 met dezelfde bevestiging en
  `uitkomst` `duplicaat`, zonder opnieuw te verwerken. Hetzelfde `id` met andere inhoud: 409.
- **Offerte.** `momentopname_hash` is de SHA-256 over de canonieke JSON (RFC 8785) van `momentopname`.
- **Akkoord.** Bij tekenen in de eigen instantie een JWS (ES256 of PS256) over de canonieke JSON
  van de velden `id`, `offerte_id`, `offerte_hash`, `ondertekenaar`, `organisatie`, `getekend_op` en `vorm`.
  De ontvanger controleert met de sleutels uit `GET /jwks` van de afzender.
- **Gegevensklassen.** Elke operatie in `grip-opdrachtverkeer` draagt `x-grip-data-class`
  (A opdracht-basis, B opdracht-financieel, C bemensing) en `x-grip-caller` (de vereiste relatie
  van de aanroeper: `opdrachtgever`, `opdrachtnemer`, `parent`, `corpus`, `peer`). De klassen D, E en F
  (tarief, kosten en KPI per persoon) komen in het contract niet voor. Namen van medewerkers
  staan alleen in `GET /doorgifte/bemensing`, voor de moederinstantie.
- **Compatibiliteit.** Ontvangers negeren onbekende velden.

## FSC

Het verkeer tussen organisaties loopt via FSC (Federated Service Connectivity).

- De dienstnamen in de FSC-directory zijn `corpus-context` en `grip-opdrachtverkeer`. Elke
  aanbieder publiceert onder dezelfde naam; de peer maakt het onderscheid.
- Een applicatie roept nooit rechtstreeks een andere organisatie aan. Ze stuurt het verzoek naar
  de eigen outway, met de header `Fsc-Grant-Hash` die aangeeft onder welk contract de aanroep valt.
  De outway haalt het token op en zet `Fsc-Authorization`; de applicatie zet die header niet zelf.
- De ontvangende applicatie krijgt het verzoek van de eigen inway. De inway geeft het peer-id van
  de aanroeper door in een header. Daaruit leidt de applicatie de relatie af (opdrachtgever,
  opdrachtnemer, moeder, corpus) en beslist ze over toegang.
- **De applicatie achter de inway mag op geen andere manier bereikbaar zijn** voor deze routes.
  Anders kan iedereen de peer-header zelf zetten. De federatieroutes luisteren dus alleen op een
  adres dat uitsluitend de inway kan bereiken.
- **Nog te verifieren:** de exacte naam van de header met het peer-id. De referentie-implementatie
  uit 2023 gebruikt `Fsc-Request-Peer-Id`; controleer dit tegen de FSC-versie die wordt uitgerold
  voordat een implementatie erop vertrouwt. Hetzelfde geldt voor `Fsc-Transaction-Id` voor logging.
- Het contract kent geen eigen `securitySchemes`: authenticatie en de toegang tot de dienst als
  geheel regelt FSC met een contract per tegenpartij. De toegang tot een enkele opdracht of node
  regelt de applicatie.

## Open punten

- **Naamruimte.** `https://grip-koppelvlakken.example/` is een plaatshouder en staat op een plek:
  `vocabulaire/kern.source.json`. Vervangen door een duurzaam domein voor versie 1.0.0.
- **Contactgegevens** in de OpenAPI-documenten (repo-adres en e-mailadres) zijn voorlopig.
- **Licentie** is nog niet gekozen.
- **Woordenlijst.** De omschrijvingen van de node-typen zijn een eerste voorstel. Welke typen tot
  de kern horen wordt met de beheerders van het corpus vastgesteld.
- **Peer-header** van de inway, zie hierboven.
