# 0034 Vacatureteksten komen uit een bibliotheek en zijn werk met een verloop

Status: aanvaard (2026-10-08)

## Context

ADR 0018 legde vast dat een vacaturetekst een concept is dat een mens vaststelt, en dat het taalmodel een concept kan opstellen met eerdere vacatures als voorbeeld. In de praktijk begon elke tekst leeg: het tabblad bood alleen "Schrijf zelf". De organisatie heeft eigen vacatureteksten die grotendeels hetzelfde zijn: wat ze biedt, waar je komt te werken en hoe je solliciteert staan in elke tekst.

Een tekst wordt ook niet door één persoon in één keer geschreven. De aanvrager schrijft, een HR-adviseur of een leidinggevende leest mee, er komen opmerkingen terug, en dat herhaalt zich.

## Besluit

**Een bibliotheek van standaardteksten per rol.** Een standaardtekst hoort bij een rol uit de rollencatalogus en bestaat uit onderdelen. Onderdelen die elke rol deelt staan één keer in de bibliotheek. Een tekst is gestructureerd: koppen, alinea's, lijsten en nadruk, geen vrije HTML. Tussen accolades staat wat de vacature of een instelling invult.

**De meegeleverde teksten zijn gegevens.** Ze staan in de repo als bestand en worden bij het starten geladen. Laden overschrijft nooit wat een mens heeft gewijzigd. Een tekst die niet van de organisatie zelf komt, is gemarkeerd als afgeleid tot iemand hem heeft gelezen.

**Twee ingangen op een vacature.** De standaardtekst van de rol invullen, of een concept op maat laten opstellen met die standaardtekst als voorbeeld. Bij een concept op maat schrijft het model alleen de onderdelen van de rol; de gedeelde onderdelen worden ingevoegd. Beide leveren een concept op, met de herkomst erbij.

**Een tekst heeft een verloop.** Bovenop de versies komen rondes van beoordeling met een oordeel per beoordelaar, en opmerkingen per onderdeel. Opslaan noemt de versie waarvan is uitgegaan en wordt geweigerd als iemand anders intussen opsloeg. Alleen de laatste versie kan worden vastgesteld, en niet zolang er iets in te vullen staat. Wie een vastgestelde tekst aanpast, begint een nieuwe ronde; tot die is vastgesteld gaat de oude tekst de deur uit.

**Wie gevraagd is te beoordelen, krijgt precies dat.** De toegangsregels kennen een nieuwe handeling, een tekst beoordelen. Die is er voor wie de vacature mag bewerken en voor wie gevraagd is. De gevraagde leest de vacature zonder namen.

**Het werk komt als taak.** Schrijven, beoordelen en opmerkingen verwerken zijn taken in het plan, gesloten door een feit.

**Het adres van de gepubliceerde vacature** wordt vastgelegd bij de vacature, per plek, naast de verwijzing naar het wervingssysteem.

## Gevolgen

- Vier nieuwe tabellen voor het verloop en de publicatie, twee voor de bibliotheek. Een versie van een tekst krijgt de herkomst "standaardtekst" erbij.
- Het plan van de takenlaag krijgt versie 2026.3. Lopende vacatures houden hun versie.
- De rollencatalogus krijgt bij het laden de rollen van de bibliotheek die er nog niet in staan.
- De motivatie is nodig voor het aanvraagformulier, maar grip weigert een aanvraag zonder vastgestelde motivatie niet. Het scherm zegt het wel. Afdwingen is een vervolgbesluit.
- Namen van personen staan nooit in een standaardtekst. Een test bewaakt dat voor de meegeleverde teksten.
- Meer over de analyse van de voorbeelden en over wat naar het model gaat staat in `docs/vacatureteksten.md`.
