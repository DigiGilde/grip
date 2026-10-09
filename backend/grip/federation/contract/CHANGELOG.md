# Changelog

Dit bestand volgt [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/). De versies volgen
[Semantic Versioning](https://semver.org/lang/nl/). Beide diensten delen een versienummer.

## [Unreleased]

### Toegevoegd in grip-opdrachtverkeer

- Offerte: `kenmerk`, `uw_kenmerk`, `afzender` en `brief` in de momentopname. De brief is de tekst bij de bedragen en hoort bij de inhoud waarover de hash wordt berekend.
- Offerteregel: `schalen` bij een personeelsregel, `jaar` bij een vast bedrag, en `maandtarieven_per_periode` voor een tarief dat binnen een kalenderjaar wijzigt. `maandtarieven_per_jaar` geldt voor een tarief dat alleen op 1 januari wijzigt.
- Vacature: `publicaties`, de openbare adressen waar de vacature te lezen is.

### Verduidelijkt in grip-opdrachtverkeer

- `GET /opdrachten` zei "geen bedragen" en gegevensklasse A, terwijl het antwoord voor een corpus-systeem `besteding` bevat. De omschrijving en de gegevensklasse (A en B) volgen nu het schema.

## [1.0.0] - 2026-10-08

De eerste versie die wordt uitgerold. De interface is Nederlands.

### Gewijzigd ten opzichte van 0.1.0

- **Nederlandse interface.** Paden, schemanamen, velden en waarden van codelijsten zijn vertaald
  naar de begrippen van het domein, zoals de NL GOV API Design Rules vragen. Termen uit
  standaarden, technische termen, de `x-`-uitbreidingen en elk `operationId` zijn niet vertaald.
  De volledige lijst staat in `docs/termen.md`.
- De opdrachtgever en de opdrachtnemer in een aanvraag en een offerte noemen verplicht hun
  `instantie_uri`. Onderdelen van een organisatie delen een TOOI-URI en zijn alleen aan hun
  instantie te onderscheiden.
- Het eindrapport kent ook het antwoord 409, zoals de regel voor idempotentie voorschrijft.
- De idempotentie van een gepusht bericht geldt per verzendende peer.
- Vacature: `id` is het id van het bericht, `uri` identificeert de vacature over berichten heen.
  De `vacatureId` in het pad van een aanbod en `vacature_id` in het aanbod zijn de uuid uit die URI.
- Akkoord en afwijzing: `organisatie` is de opdrachtgever en, bij een akkoord uit de eigen
  instantie, de afzender. De ontvanger volgt uit de offerte.

### Toegevoegd in grip-opdrachtverkeer

- `GET /openapi.json`: het contract dat de instantie volgt, als operatie in het contract zelf.
- `maandtarieven_per_jaar` op een personeelsregel van een offerte die over tariefjaren met een
  verschillend tarief loopt.
- `errors` in een probleembericht, voor de afwijkingen van een bericht dat niet aan het schema
  voldoet.
- `besteding` op een opdracht: besteding in totalen, alleen in het antwoord aan een
  corpus-systeem waar de opdracht naar verwijst.
- Doorgifte van bemensing kan aantallen per rol bevatten (`aantal`) in plaats van personen.

### Verduidelijkt in corpus-context

Naast de vertaling alleen omschrijvingen; geen veld is verplicht geworden.

- `naamruimte` in de woordenlijst is de naamruimte van de eigen typen van het corpus. Kerntypen
  dragen altijd de naamruimte van de kernlijst.
- Keten: een politieke input en een node uit een ander corpus zijn eindpunten, de paden zijn
  kortste paden, en de keten van een politieke input zelf is alleen die node.
- Periode: de einddatum is inclusief; wie intern een exclusieve einddatum voert rekent om.
- Omschrijving van een node: platte tekst, opmaak verwijderd, zonder labels van vermeldingen.
- Peildatum voor de eerste vastlegging in de historie: de eerst bekende titel en status.
- Beherende organisatie van een eenheid zonder eigen TOOI-URI: de dichtstbijzijnde geregistreerde
  bovenliggende organisatie met het kenmerk van de eenheid, anders de organisatie van het corpus.

## [0.1.0] - 2026-10-08 (nooit uitgerold)

De eerste opzet, met een Engelse interface. Vervangen door 1.0.0 voordat iets ervan in gebruik
kwam.

### Toegevoegd

- `corpus-context` v1: corpus, woordenlijst, node ophalen met peildatum, keten naar de politieke
  input, nodes zoeken.
- `grip-opdrachtverkeer` v1: aanvraag, offerte, akkoord en afwijzing, voortgang, uitputting,
  factuurgegevens, eindrapport, vacature en aanbod, doorgifte aan de moederinstantie, opdrachten
  bij een node, sleutelset.
- JSON Schema per object, kernwoordenlijst van tien node-typen en twaalf edge-typen,
  JSON-LD-context, voorbeelden.
