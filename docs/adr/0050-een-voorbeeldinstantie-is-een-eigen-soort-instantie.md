# 0050 Een voorbeeldinstantie is een eigen soort instantie

Status: aanvaard (2026-10-09)

## Context

Een uitgerolde instantie begint leeg, en de voorbeeldgegevens laden alleen in een lokale ontwikkelinstantie. Wie grip wil laten zien, of een eerste uitrol wil proberen zonder echte gegevens, had daardoor geen weg: lokaal draaien of echte gegevens invoeren.

Voorbeeldgegevens in een instantie voor echt werk zijn geen optie. Een verzonnen offerte naast een echte is niet meer van elkaar te onderscheiden, en een document met het Rijkslogo dat nergens over gaat mag niet bestaan.

## Besluit

**Eén instelling maakt een instantie een voorbeeld.** `INSTANCE_MODE=voorbeeld`. Zonder die instelling verandert er niets: een instantie begint leeg en de eerste beheerder komt uit `BOOTSTRAP_BEHEERDER_EMAILS`.

**Een voorbeeldinstantie vult zichzelf.** Bij de eerste start op een lege database laadt ze de verzonnen voorbeeldgegevens, één keer. Elke nacht (`EXAMPLE_RESET_HOUR`, via de worker) en met `just example-reset` gaat ze terug naar die beginstand.

**De scheiding dwingt de server af, in beide richtingen.** Een voorbeeldinstantie weigert te starten op een database waarin al personen staan. Een database die als voorbeeld is gevuld draagt een markering (`instance.example` in `instance_setting`), en een instantie voor echt werk weigert daarop te starten. Een voorbeeldinstantie gooi je weg; ze wordt nooit een echte.

**Een voorbeeldinstantie wisselt niets uit.** Federatie, Wies, de sleutels voor uitvoer en voor de gebeurtenissenstroom en `BOOTSTRAP_BEHEERDER_EMAILS` zijn een startfout. Mail, meldingen, het Rijkslogo en het huisstijllettertype worden uitgezet, ook als het platform ze aanreikt.

**Inloggen blijft echt.** Een bezoeker meldt zich aan bij de identiteitsprovider. Staat het bevestigde adres op de lijst `EXAMPLE_VISITORS` (domeinen of adressen, standaard niemand), dan komt de bezoeker binnen zonder eigen persoon en kijkt als een van de voorbeeldpersonen. Die keuze staat in de sessie op de server. Het ontwikkelcookie `grip_dev_person` doet uitgerold niets, in geen van beide soorten.

**Wat een bezoeker doet draagt twee namen.** De gebeurtenis heeft de voorbeeldpersoon als handelende persoon en `bezoeker:<adres>` als verwijzing. Aanmelden en wisselen zijn eigen gebeurtenissen (`login.visited`, `login.switched`).

**Alles zegt dat het een voorbeeld is.** Het label in de balk en een regel op elke pagina komen uit de soort instantie, niet uit de naam. Elk document (offerte, factuurverzoek, ingevuld aanvraagformulier, akkoordverklaring) draagt "Voorbeeld, geen echt document". De ondertekende akkoordverklaring heeft daarvoor het lid `instantie.voorbeeld`.

## Gevolgen

- Een voorbeeldinstantie krijgt een eigen project op het platform met een eigen database, nooit het project voor echt werk.
- De code staat op één plek, `grip/core/example.py`, en de controles in `Settings._validate_instance_mode`. Een nieuw kanaal naar buiten krijgt daar een regel bij.
- Een nieuw soort document neemt de vermelding over via `Letterhead.example`.
- Lokale ontwikkeling is geen voorbeeldinstantie en werkt als voorheen: `just seed` met de hand.
- De voorbeeldgegevens hebben vaste jaren (2025 tot en met 2028). Ze verschuiven niet mee met de dag waarop de instantie start; dat is nog open.
