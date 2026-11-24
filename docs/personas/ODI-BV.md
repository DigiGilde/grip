---
code: ODI-BV
naam: Bas Bedrijfsvoering
rol: Directeur bedrijfsvoering
organisatie: Rijksorganisatie Voorbeeld ODI
eenheid: Directie Bedrijfsvoering ODI
fgr:
  functie: Topmanager
  familie: Lijnmanagement
  schaal: "16-18"
  url: https://www.functiegebouwrijksoverheid.nl/functiegebouw/functiefamilies/lijnmanagement/topmanager-s16-18
  inschatting: true
mandaat:
  tekst: "Naar het voorbeeld van het Mandaatbesluit BZK 2025: directeur bij ODI tot € 5.000.000 per verplichting. Dat dit voor de directeur bedrijfsvoering geldt, is een aanname"
  bron: https://wetten.overheid.nl/BWBR0051453/
grips:
  - instantie: Rijksorganisatie Voorbeeld ODI
    toegang: account
    rechten: [lezer]
    relaties: []
    voorbeeldpersoon: null
    dataset: null
  - instantie: DigiGilde voorbeeld
    toegang: via-federatie
    rechten: []
    relaties: []
    voorbeeldpersoon: null
    dataset: null
---

# ODI-BV Bas Bedrijfsvoering

## Wie

Bas is directeur bedrijfsvoering van ODI: financiën, personeel en huisvesting van het hele agentschap. In de tertaalrapportage is hij degene met wie de financiële cijfers van de onderdelen worden afgestemd, zodat ze kloppen met de administratie van ODI.

## Verantwoordelijk voor

- De financiële administratie en de planning-en-controlcyclus van ODI.
- De afstemming van de financiële cijfers in de tertaalrapportage met de directeur digitalisering en de andere directeuren.
- Advies over vacatures en inhuur waar het budget van ODI het vraagt [aanname].

## Mandaat en handtekening

Naar het voorbeeld van het Mandaatbesluit BZK 2025 (bijlage 1) gaat een directeur bij ODI verplichtingen aan tot € 5.000.000 ([bron](https://wetten.overheid.nl/BWBR0051453/)). Of dat voor deze functie geldt, is een aanname.

## Wat die nodig heeft

- Per tertaal de cijfers van elk onderdeel naast zijn eigen administratie: omzet, kosten, overhead en dekking.
- Een stand die vaststaat tot de rapportage is verstuurd, zodat later gewijzigde cijfers zichtbaar zijn.
- Waar het gilde en de administratie van ODI verschillen, met de reden.

## Ritme

- Per tertaal de afstemming met de directeur digitalisering ([ODI-DIG](ODI-DIG.md)) en de business controller ([ODI-BC](ODI-BC.md)) [aanname].
- Maandelijks de financiële stand van het agentschap [aanname].

## In Grip

**Rijksorganisatie Voorbeeld ODI** (account, lezer; de moederinstantie van DigiGilde). In de voorbeelden bestaat die instantie nog niet: er zijn er drie, DigiGilde voorbeeld, Voorbeeldministerie en Voorbeeldprogramma. Wat hieronder staat, is wat de bestaande doorgifte van DigiGilde aan de moeder oplevert, niet wat een scherm toont.

**DigiGilde voorbeeld** (via federatie). Hij leest de kosten met overhead en dekking en de factuurgegevens die het gilde doorgeeft, naast de omzet.

De moeder haalt op wat het gilde doorgeeft: opdrachten met status en bedragen, factuurgegevens, bezetting en capaciteit als aantallen per rol (namen alleen als de beheerder van het gilde dat aanzet), en kosten met overhead en dekking (ADR 0016, `docs/architectuur.md`). Klasse D t/m F blijven in het gilde. De routes bestaan met tests en worden nog niet gebruikt.

## Wat Grip nog niet kan

- **ODI als instantie.** Er is geen voorbeeldinstantie voor ODI en geen scherm voor de moeder; de doorgifte bestaat als route.
- **Tertaalrapportage.** Rapportage staat per jaar, niet per tertaal.
- **Afstemmen met bedrijfsvoering.** Geen vastgestelde stand per tertaal en geen plek waar een verschil met de administratie een reden krijgt.
- **Verrekenen tussen onderdelen.** Of het gilde factureert of doorbelast, staat open.

## Bronnen

- [Mandaatbesluit BZK 2025](https://wetten.overheid.nl/BWBR0051453/), bijlage 1, ODI
- [Functiegebouw Rijk, Topmanager](https://www.functiegebouwrijksoverheid.nl/functiegebouw/functiefamilies/lijnmanagement/topmanager-s16-18). De schaal is een inschatting; een directeur in een agentschap kan binnen 16-18 hoger zitten
