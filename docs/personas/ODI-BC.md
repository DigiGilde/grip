---
code: ODI-BC
naam: Bo Begroting
rol: Business controller
organisatie: Rijksorganisatie Voorbeeld ODI
eenheid: Directie Bedrijfsvoering ODI
fgr:
  functie: Senior Adviseur Bedrijfsvoering
  familie: Bedrijfsvoering
  schaal: "11-13"
  url: https://www.functiegebouwrijksoverheid.nl/functiegebouw/functiefamilies/bedrijfsvoering/senior-adviseur-bedrijfsvoering
  inschatting: true
mandaat:
  tekst: "Geen mandaat om te verplichten; adviseert en toetst. Het Mandaatbesluit BZK 2025 noemt voor ODI geen controller"
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

# ODI-BC Bo Begroting

## Wie

Bo is business controller bij ODI en doet de afstemming van de financiële cijfers in de tertaalrapportage zelf: ze legt de cijfers van het gilde naast de administratie, zoekt uit waar ze verschillen en meldt dat aan de directeur bedrijfsvoering ([ODI-BV](ODI-BV.md)). Dat zij het doet in plaats van de directeur, is een aanname.

## Verantwoordelijk voor

- De financiële cijfers in de tertaalrapportage over de onderdelen onder digitalisering.
- Het verschil tussen wat het gilde meldt en wat de administratie van ODI heeft, met de reden.
- Advies aan het hoofd van het gilde en de directeur digitalisering over kosten, overhead en dekking [aanname].

## Mandaat en handtekening

Geen mandaat [aanname]. Zij adviseert en toetst; de directeur bedrijfsvoering stelt de cijfers vast.

## Wat die nodig heeft

- Per tertaal de cijfers van het gilde in dezelfde indeling als haar administratie.
- Een verschil per opdracht of kostenpost met de reden erbij, in plaats van een mailwisseling.
- De factuurgegevens en kosten met overhead en dekking, per periode.

## Ritme

- Per tertaal de afstemming met het hoofd van het gilde ([GLD-MGR](GLD-MGR.md)) en de directeur digitalisering ([ODI-DIG](ODI-DIG.md)) [aanname].
- Maandelijks de administratie naast de aangeleverde maanden van het gilde [aanname].

## In Grip

**Rijksorganisatie Voorbeeld ODI** (account, lezer; de moederinstantie van DigiGilde). In de voorbeelden bestaat die instantie nog niet: er zijn er drie, DigiGilde voorbeeld, Voorbeeldministerie en Voorbeeldprogramma. Wat hieronder staat, is wat de bestaande doorgifte van DigiGilde aan de moeder oplevert, niet wat een scherm toont.

**DigiGilde voorbeeld** (via federatie). Ze leest factuurgegevens en kosten met overhead en dekking van de opdrachten. Ze legt zelf niets vast.

De moeder haalt op wat het gilde doorgeeft: opdrachten met status en bedragen, factuurgegevens, bezetting en capaciteit als aantallen per rol (namen alleen als de beheerder van het gilde dat aanzet), en kosten met overhead en dekking (ADR 0016, `docs/architectuur.md`). Klasse D t/m F blijven in het gilde. De routes bestaan met tests en worden nog niet gebruikt.

## Wat Grip nog niet kan

- **ODI als instantie.** Er is geen voorbeeldinstantie voor ODI en geen scherm voor de moeder; de doorgifte bestaat als route.
- **Tertaalrapportage.** Rapportage staat per jaar, niet per tertaal.
- **Afstemmen met bedrijfsvoering.** Geen gedeelde stand per tertaal waarop zij en het gilde dezelfde cijfers zien, en geen plek voor het verschil.

## Bronnen

- [Mandaatbesluit BZK 2025](https://wetten.overheid.nl/BWBR0051453/), bijlage 1, ODI
- [Functiegebouw Rijk, Senior Adviseur Bedrijfsvoering](https://www.functiegebouwrijksoverheid.nl/functiegebouw/functiefamilies/bedrijfsvoering/senior-adviseur-bedrijfsvoering). Business controller is geen functiegroep; de groep is een inschatting
