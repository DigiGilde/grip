# Bijdragen

## Een wijziging voorstellen

1. Open een issue met wat je nodig hebt en waarom. Noem welke dienst het raakt en welke
   implementaties moeten meebewegen.
2. Maak een pull request met de wijziging in het schema of het OpenAPI-document, minstens een
   geldig voorbeeld, en waar zinvol een ongeldig voorbeeld dat moet falen.
3. Werk `CHANGELOG.md` bij onder `Unreleased`.
4. `just check` moet slagen. Draai `just build` als je een schema of de woordenlijst wijzigt; de
   gegenereerde bestanden (`vocabulaire/kern.json`, `vocabulaire/README.md`, `context.jsonld`)
   horen in dezelfde wijziging.
5. Een wijziging die een bestaande implementatie breekt heeft instemming nodig van de beheerders
   van elke implementatie.

Bewerk gegenereerde bestanden niet met de hand. De woordenlijst wijzig je in
`vocabulaire/kern.source.json`.

## Versies

Beide diensten delen een versienummer. Het staat in `info.version` van beide OpenAPI-documenten en
in `package.json`.

| Soort wijziging | Voorbeeld | Versie |
|---|---|---|
| Patch | Omschrijving verduidelijkt, voorbeeld toegevoegd | 1.0.0 naar 1.0.1 |
| Minor | Optioneel veld, nieuwe operatie, nieuw kerntype | 1.0.0 naar 1.1.0 |
| Major | Veld verwijderd of verplicht gemaakt, betekenis gewijzigd, codelijst ingekort | 1.x naar 2.0.0, nieuw pad `/v2` |

- Ontvangers negeren onbekende velden; daardoor is een minor-versie veilig.
- Een waarde toevoegen aan een codelijst (bijvoorbeeld een status) is een minor-wijziging.
  Ontvangers moeten een onbekende waarde kunnen tonen zonder te falen.
- Bij een major-versie blijft de vorige versie een afgesproken periode naast de nieuwe bestaan.
- Een implementatie meldt de volledige versie die ze volgt in de header `API-Version`.

## Woordenlijst

Een type toevoegen aan de kernlijst is een minor-wijziging. Een type verwijderen of van betekenis
veranderen is een major-wijziging. Een eigen type hoort in de naamruimte van het corpus dat het
gebruikt; zie `vocabulaire/README.md`.

## Stijl

- Velden, paden en codelijsten in het Engels; titels en omschrijvingen in het Nederlands.
- Geen persoonsnamen en geen echte bedragen in voorbeelden. Gebruik het domein `.example`.
