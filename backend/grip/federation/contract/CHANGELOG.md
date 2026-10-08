# Changelog

Dit bestand volgt [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/). De versies volgen
[Semantic Versioning](https://semver.org/lang/nl/). Beide diensten delen een versienummer.

## [Unreleased]

## [1.1.0-alpha.1] - 2026-10-08

### Gewijzigd in grip-opdrachtverkeer

- De opdrachtgever en de opdrachtnemer in een aanvraag en een offerte noemen verplicht hun
  `instance_uri`. Onderdelen van een organisatie delen een TOOI-URI en zijn alleen aan hun
  instantie te onderscheiden. Dit is de enige wijziging waar een afzender van 1.0 iets voor moet
  doen.
- Het eindrapport kent nu ook het antwoord 409, zoals de regel voor idempotentie al voorschreef.
- De idempotentie van een gepusht bericht geldt per verzendende peer.
- Vacature: `id` is het id van het bericht, `uri` identificeert de vacature over berichten heen.
  De `vacancyId` in het pad van een aanbod en `vacancy_id` in het aanbod zijn de uuid uit die URI.
- Akkoord en afwijzing: `organisation` is de opdrachtgever en, bij een akkoord uit de eigen
  instantie, de afzender. De ontvanger volgt uit de offerte.

### Toegevoegd in grip-opdrachtverkeer

- `GET /openapi.json`: het contract dat de instantie volgt, als operatie in het contract zelf.
- `monthly_rates_per_year` op een personeelsregel van een offerte die over tariefjaren met een
  verschillend tarief loopt.
- `errors` in een probleembericht, voor de afwijkingen van een bericht dat niet aan het schema
  voldoet.
- `spending` op een opdracht: besteding in totalen, alleen in het antwoord aan een corpus-systeem
  waar de opdracht naar verwijst.
- Doorgifte van bezetting kan aantallen per rol bevatten (`headcount`) in plaats van personen.

### Verduidelijkt in corpus-context

Alleen omschrijvingen; geen veld is hernoemd of verplicht geworden. Een implementatie van 1.0
blijft voldoen.

- `namespace` in de woordenlijst is de naamruimte van de eigen typen van het corpus. Kerntypen
  dragen altijd de naamruimte van de kernlijst.
- Keten: een politieke input en een node uit een ander corpus zijn eindpunten, de paden zijn
  kortste paden, en de keten van een politieke input zelf is alleen die node.
- Periode: de einddatum is inclusief; wie intern een exclusieve einddatum voert rekent om.
- Omschrijving van een node: platte tekst, opmaak verwijderd, zonder labels van vermeldingen.
- Peildatum voor de eerste vastlegging in de historie: de eerst bekende titel en status.
- Beherende organisatie van een eenheid zonder eigen TOOI-URI: de dichtstbijzijnde geregistreerde
  bovenliggende organisatie met het kenmerk van de eenheid, anders de organisatie van het corpus.

## [1.0.0-alpha.1] - 2026-10-08

### Toegevoegd

- `corpus-context` v1: corpus, woordenlijst, node ophalen met peildatum, keten naar de politieke
  input, nodes zoeken.
- `grip-opdrachtverkeer` v1: aanvraag, offerte, akkoord en afwijzing, voortgang, uitputting,
  factuurgegevens, eindrapport, vacature en aanbod, doorgifte aan de moederinstantie, opdrachten
  bij een node, sleutelset.
- JSON Schema per object, kernwoordenlijst van tien node-typen en twaalf edge-typen,
  JSON-LD-context, voorbeelden.
