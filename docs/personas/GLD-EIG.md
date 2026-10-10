---
code: GLD-EIG
naam: Priya Product
rol: Opdrachteigenaar en opdrachtmanager
organisatie: DigiGilde voorbeeld
eenheid: Vakgroep Advies en product
fgr:
  functie: Project-/Programmamanager
  familie: Project-/Programmamanagement
  schaal: "12-15"
  url: https://www.functiegebouwrijksoverheid.nl/functiegebouw/functiefamilies/project---programmamanagement/project--programmamanager
  inschatting: false
mandaat:
  tekst: "Geen mandaat om te verplichten; maakt de offerte, het hoofd van het gilde ondertekent"
  bron: aanname
grips:
  - instantie: DigiGilde voorbeeld
    toegang: account
    rechten: []
    relaties: [eigenaar, lid, zelf]
    voorbeeldpersoon: Priya Product
    dataset: voorbeeld
  - instantie: Voorbeeldprogramma
    toegang: via-federatie
    rechten: []
    relaties: []
    voorbeeldpersoon: null
    dataset: null
---

# GLD-EIG Priya Product

## Wie

Priya is eigenaar van een handvol opdrachten van het gilde, waaronder het werk voor het Voorbeeldprogramma. Ze maakt de begroting en de offerte, zorgt dat de rollen gevuld raken en sluit elke maand af. Ze werkt zelf ook mee op een van haar opdrachten.

## Verantwoordelijk voor

- Begroting en offerte van haar opdrachten, tot het akkoord van de opdrachtgever.
- De uitvoering: rollen gevuld, maanden afgesloten, per factuurperiode aangeleverd, facturen vastgelegd.
- Het eindrapport aan het eind van een opdracht.

## Mandaat en handtekening

Geen mandaat om te verplichten [aanname]. Zij maakt de offerte; de handtekening van het gilde staat er namens het hoofd onder ([GLD-MGR](GLD-MGR.md)). Wie een offerte maakte, keurt haar niet goed en tekent er niet voor als opdrachtgever (ADR 0048).

## Wat die nodig heeft

- Per opdracht: begroot, gerealiseerd, nog gepland, verwacht totaal en de afwijking.
- Wie er op haar opdrachten staat, met inzetbedrag en categorie.
- Wanneer een maand afgesloten en een periode aangeleverd moet zijn.

## Ritme

- Maand afsluiten binnen vijf werkdagen, aanleveren binnen vijf werkdagen na een factuurperiode, factuur vastleggen binnen tien.
- Voortgangsoverleg met de opdrachtgever, maandelijks of per sprint [aanname].

## In Grip

**DigiGilde voorbeeld** (account, geen recht in grip, eigenaar van opdrachten). Zij landt op Start en ziet Start, Taken, Opdrachten, Team, Vacatures, Financieel en Rapportage.

- "Een opdracht winnen": begroting, offerte, interne goedkeuring vragen, aanbieden (via de grip van de opdrachtgever, met een tekenlink of als document), het akkoord vastleggen, in uitvoering zetten.
- "Een opdracht uitvoeren en factureren": maanden afsluiten, aanleveren, factuur vastleggen, naverrekening, eindrapport.
- "Iemand werven": een vacature voor een rol op haar opdracht.
- Onder Financieel, Kosten dekt zij een kostenpost die het programma bij het gilde vraagt, met "Gevraagd door" erbij, met een begrotingsregel van haar opdracht (ADR 0052).

**Voorbeeldprogramma** (via federatie). De offerte gaat via de grip van het programma; het akkoord, en het verzoek om een kostenpost, komen terug. Het programma leest die kostenpost bij het gilde.

## Wat Grip nog niet kan

- **Verlengen of groeien na akkoord.** Een aanvullende offerte is ontworpen, niet gebouwd.
- **Verrekenen tussen onderdelen.** Of haar aanlevering een factuur of een doorbelasting wordt, staat open.
- **Overleg.** Het voortgangsoverleg met de opdrachtgever leeft buiten grip.
- **Eigenaar bij binnenkomst.** Een binnengekomen aanvraag krijgt pas een eigenaar als de beheerder haar aanwijst.

## Bronnen

- [Functiegebouw Rijk, Project-/Programmamanager](https://www.functiegebouwrijksoverheid.nl/functiegebouw/functiefamilies/project---programmamanagement/project--programmamanager)
- [werkstromen.md](../werkstromen.md)
- ADR 0039, ADR 0048, ADR 0052
