# 0019 Het koppelvlak is Nederlands, de code Engels

Status: aanvaard (2026-10-08)

## Context

De contracten voor `corpus-context` en `grip-opdrachtverkeer` kregen bij de eerste opzet Engelse paden en velden, in lijn met de regel dat code in deze repo Engels is. De waarden voor node-typen en edge-typen waren al Nederlands, omdat ze uit Bouwmeester komen. Het resultaat was een gemengd koppelvlak.

De API Design Rules van de overheid vragen een interface in het Nederlands, tenzij er een officieel Engelstalig begrippenkader bestaat. Dat bestaat voor dit domein niet. De standaard valt onder pas-toe-of-leg-uit, en "de bouwers schrijven liever Engels" is geen uitleg die standhoudt.

Op het moment van dit besluit waren er twee implementaties, allebei van ons en geen van beide uitgerold. Later hernoemen breekt elke organisatie die is aangesloten.

## Besluit

Het koppelvlak tussen organisaties is Nederlands: paden, schema's, velden en codelijsten gebruiken de termen uit de begrippenlijst (opdracht, offerte, akkoord, uitputting, factuurgegevens, vacature). Termen uit standaarden en technische termen blijven zoals ze zijn (id, uri, hash, jws, jwks).

De code van grip en van Bouwmeester blijft Engels. De vertaling tussen contracttermen en codenamen staat op een plek, in de federatiemodule.

De Engelse versie van het contract is nooit uitgebracht en heet achteraf 0.1.0. De Nederlandse versie is 1.0.0.

## Gevolgen

- Wie het contract leest, een beleidsmedewerker of een bouwer bij een andere organisatie, ziet dezelfde woorden als in de schermen en in de documentatie.
- Er is een vertaallaag aan de rand. De begrippenlijst in `docs/domein.md` is de bron voor die vertaling: UI-term, codenaam en nu ook contractterm.
- De implementatie in Bouwmeester moet worden aangepast aan de Nederlandse versie voordat ze wordt aangeboden.
- De interne API van grip, tussen de eigen frontend en backend, is geen koppelvlak tussen organisaties en blijft Engels.
