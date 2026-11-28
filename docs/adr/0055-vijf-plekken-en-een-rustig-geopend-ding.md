# 0055 Vijf plekken en een rustig geopend ding

Status: aanvaard (2026-11-04)

Vervangt: [0033 De hoofdnavigatie volgt het werk en de lezer](0033-hoofdnavigatie-volgt-het-werk-en-de-lezer.md), [0042 Zeven plekken in de hoofdbalk, en een tweede balk voor pagina's die bij elkaar horen](0042-zeven-plekken-en-een-tweede-balk.md)

Stelt bij: [0039 Afsluiten per maand, aanleveren per factuurperiode](0039-afsluiten-per-maand-aanleveren-per-periode.md), [0044 Een verloop per zaak, uit dezelfde feiten als de taken](0044-een-verloop-per-zaak-uit-dezelfde-feiten-als-de-taken.md)

## Context

Grip was niet diep, maar druk. De weg naar het werk was kort: hooguit drie klikken, de zwaarste taken twee tot vijf. Maar je koos steeds tussen te veel gelijke dingen, je las hetzelfde op veel plekken in andere woorden, en voor elk stuk werk stond een grote kop.

- De balk had zeven plekken en een tweede balk (ADR 0042). Start, Taken, Financieel en Rapportage overlapten: de startpagina toonde taken, aandachtspunten en een tabel per opdracht, Taken nog eens de taken, Financieel en Rapportage elk een deel van het geld.
- Een opdracht opende op de tab Overzicht, onder een kop met de stand, de kerncijfers en een stappenbalk, met acht tabs eronder. Een vacature had een stappenbalk en tabs: twee navigaties over één lijn.
- De woorden liepen door elkaar. Team was de plek met alle mensen en ook wie op een opdracht werkt, Bemensing een derde woord daarvoor. Gerealiseerd stond op één pagina als € 73.450 en als € 68.800. Open rollen had drie betekenissen en drie aantallen. Pijplijn stond op het scherm, terwijl de eigen regel het verbiedt.

Veertien onderzoeksrapporten, over persona's, de structuur, het designsysteem en een voorbeeld, met een tegenstem en een toets, zijn samengevat in een voorstel met een wegwerpschets. Drie andere richtingen zijn ernaast gelegd: de plekken houden en alles aanscherpen, alleen rijen zonder wisselbalk, en Start als het menu. De opdrachtgever koos op 4 november 2026 voor vijf plekken met een smalle wisselbalk op een breed scherm, en voor dezelfde patronen als een dienst voor burgers, zonder een aparte kant voor wie aanvraagt of tekent.

## Besluit

**Vijf plekken.** Start, Opdrachten, Vacatures, Mensen en Geld. Aanvragen staat erbij voor wie aanvraagt of tekent; Beheer staat apart aan het eind. Een teamlid ziet drie plekken, een aanvrager of tekenbevoegde drie, een planner vier, een lezer vier, een eigenaar vijf en de beheerder vijf plus Beheer. Taken gaat op in Start; het adres `/taken` blijft, met het bord, Wacht op anderen en de offertes ter goedkeuring. De plek Team heet Mensen. Financieel en Rapportage gaan op in Geld en Mensen. De tweede balk vervalt. De balk biedt alleen aan wat iets voor de lezer kan bevatten; dat is een hulp en geen toegangsregel.

**De balk is die van het designsysteem.** De plekken staan in `nldd-tab-bar` als navigatie, in de werkbalk van de schil, met de plek waar je bent als gevuld vlak, zoals het designsysteem dat tekent. Wat niet past staat achter "Meer tabs", en de plek waar je bent blijft in de balk. In het midden staat het zoekveld, aan het eind Beheer en het account. Op een smal scherm staan de plekken onderaan als icoon met hun woord, met als laatste Ik: het account als pagina. Het aantal taken staat bij Start. Het merk staat met de naam van de organisatie op een breed scherm; onder 1200 pixels staat alleen het merk, en op een smal scherm niets.

**Start zegt wat er voor jou ligt.** Eén kolom, in dezelfde volgorde voor iedereen, zonder filters, jaarkeuze of volgordekeuze. Eerst Te doen: per zaak één rij met de eerstvolgende taak en wat erna komt, hooguit vijf zaken, en altijd "Alle taken". Dan wat voor jou speelt, in blokken die volgen uit je rechten en relaties en nooit uit een instelling. Een blok staat er alleen als het iets voor je bevat, en toont hooguit acht rijen. Dan Nieuw: de laatste drie gebeurtenissen. "Wat vraagt aandacht" bestaat niet meer: wat iemand kan oplossen is een taak, wat over een opdracht gaat staat in de rij van die opdracht. Op Start staat niets van de klassen D, E en F.

**Een geopend ding landt op wat nu moet.** Een opdracht opent op haar landing: de link terug, de naam, de ene knop, een regel over voor wie, wanneer en waar ze staat, de zin wat er nu moet, de kerncijfers één keer, en haar onderdelen als rijen. Een rij meldt, ze rapporteert niet: heeft ze niets te melden, dan staat er alleen de naam. De rijen staan in een vaste volgorde: Afsluiten en factureren, Begroting, Offerte, Team, Eindrapport, Gegevens, Geschiedenis. Ze komen en gaan met de fase; de volgorde verspringt niet. De server beslist welke rijen er zijn en wat ze zeggen, per gegevensklasse. Een taak wijst nooit naar een onderdeel zonder rij. Een vacature opent op haar stappen als rijen, elk met haar stand: Aanvraag, Advies en akkoord, Tekst en openstellen, Vervullen. Twee stappen mogen tegelijk aan de beurt zijn. Een stappenbalk is er niet meer: het verloop is één regel tekst.

**Een onderdeel is een eigen pagina** met een eigen adres: terug naar het ding, de naam van het onderdeel als titel, de ene knop van dat onderdeel, en op een breed scherm de wisselbalk met de andere onderdelen. Op een smal scherm wissel je via de landing. De tabs worden onderdelen. Financieel en Begroting worden samen Begroting, met een vorm per fase: tot het akkoord de invoer, daarna per regel zeven kolommen met een totaalrij over de hele looptijd. Overzicht wordt Gegevens, Bemensing wordt Team, de tab Taken wordt "Alle taken van deze opdracht".

**Drie soorten scherm.** Een lijst: een leeskolom met rijen en één hoofdknop. Een werkblad: de volle breedte, alle kolommen van een rekenregel in één rij, met een totaalrij. Een stuk: één ding dat je als geheel leest. Elke pagina zegt wat ze is; welk scherm wat is staat vast in `docs/ontwerp.md`. De toets bij de hoofdvraag van een scherm: kun je het antwoord uit één rij lezen, zonder iets op te tellen of te vergelijken? Dan een lijst, anders een werkblad.

**Eén vorm om te wisselen: de balk met onderlijn.** De onderdelen van een ding en de weergaven van een lijst staan in `TabNav`, elk een pagina met een eigen adres. Opdrachten heeft Potentieel, Lopend en Afgesloten; Vacatures Alle vacatures en Opengesteld; Mensen de lijst, het bord, Bezetting en Declarabiliteit, alleen wat de lezer heeft. Een planner landt op het bord, en het bord toont alle open rollen, ook die met een lopende vacature. Er is geen keuzelijst voor een weergave. Geld en Beheer zijn overzichtspagina's met rijen die melden wat ertoe doet; de keuze van het jaar staat op de pagina die erop reageert.

**Eén accent.** In de inhoud is de hoofdknop het enige gevulde vlak. De hoofdbalk is navigatie en volgt het designsysteem; de reden van de regel, twee gelijke vlakken onder elkaar, geldt daar niet. Een stand op een rij is een `nldd-badge`.

**Eén plek per feit, één woord per ding.** Team is wie op een opdracht werkt, Mensen is de plek. Potentieel, nooit pijplijn; de Engelse namen in de code (`pipeline_cents`) blijven. Gerealiseerd is inzet plus gerealiseerde kosten; waar de kolommen optellen tot het verwacht totaal heet de inzet Gerealiseerde inzet. Een open rol is een rol zonder persoon, ook met een lopende vacature; een opengestelde vacature heet vacature. Geschiedenis blijft het woord op een zaak. Vakwoorden als Begroot, Offerte, Akkoord, FTE, Naverrekening en Uitputting blijven: grip is werk.

**Zoeken versnelt en vervangt niets.** Eén zoekveld voor namen, in de balk en op een smal scherm bovenaan Start. Het vindt opdrachten, vacatures en mensen, en alleen wat de lezer mag openen.

**Tekenen heeft één lichte vorm.** Een gast met een tekenlink en wie met een account een ontvangen offerte opent, zien dezelfde pagina: het bedrag bovenaan, twee knoppen, het kenmerk achter Details, en de vraag naar de functie pas in het paneel na "Geef akkoord". Ze delen de vorm, niet de logica.

**Geen oud adres blijft.** Elk onderdeel en elke weergave heeft een eigen adres. De plekken `/team`, `/inzet`, `/kosten`, `/factureren` en `/rapportage`, en de tabs van een opdracht en een vacature, vervallen zonder doorverwijzing: grip heeft nog geen gebruikers.

## Gevolgen

- Op papier geteld over 84 taken uit de persona-rapporten: 31 beter, 46 gelijk en 7 slechter. Wat slechter blijft:
  - Het geld over opdrachten heen staat niet meer op Start maar onder Geld, op Lopende opdrachten: voor wie het geld leest van nul naar twee klikken. De drie kerncijfers blijven op Start.
  - Geld is een stap: een factuur op een kostenpost gaat voor de beheerder van drie naar vier klikken, de lijst bijlagen van een naar twee, al meldt de rij het aantal.
  - De bezetting als getal is voor een leidinggevende een klik verder, al staan haar mensen op Start.
  - Alle taken en Nieuwe taak zijn een klik verder, omdat Taken uit de balk is.
- Bij het bouwen bewust weggevallen: de tabel per opdracht op Start (de naam op Start opent altijd de landing), en op Lopende opdrachten de afgesloten opdrachten, het subtotaal "Als alles doorgaat" en de keuze van de volgorde. Afgesloten opdrachten staan op Jaarverantwoording, het potentieel op Potentieel.
- Smaller dan op main, bij de eindreview gevonden:
  - Alle taken van een zaak, het onderdeel Taken van een opdracht of vacature, is er alleen voor wie de taken mag wijzigen. Een lezer zag ze eerst wel. De taken van de lezer zelf blijven op Start en onder Taken.
  - Begroting vóór het akkoord toont alleen de invoer. De signalen en de inzet per maand, die op main ook bij een potentiële opdracht stonden, komen na het akkoord (besluit V10).
  - Wat van Lopende opdrachten wegviel staat in `docs/openstaand.md`, onder "Lopende opdrachten".
- Een rij en een blok op Start hebben elk een gegevensklasse en een lektest, per fase en per soort lezer: tientallen zinnen. De zin van een rij komt uit één pure functie (`parts_of`), die Start ook gebruikt. Wat elke rij en elk blok mag zeggen staat in `docs/toegang.md`.
- Te doen per zaak is een nieuwe bewerking van de taken. Taken zonder termijn staan achteraan; daarom gaat de laatste van de vijf plekken naar de eerste zaak zonder termijn als die anders wegvalt. Het getal bij Start in de balk en "Alle taken" tellen hetzelfde.
- Start vraagt in één verzoek naar taken, rijen, het bord en geld. Warm blijft het binnen het budget van `docs/snelheid.md`; het eerste verzoek na een wijziging zit boven de vijftig statements. Op een database van ware grootte is het nog niet gemeten.
- De navigatiebalk van het designsysteem heeft één tabstop; de andere plekken bereik je met de pijlen. De oude menubalk had een tabstop per plek. Op 320 pixels staan plekken achter "Meer tabs", bij de beheerder al op 390 en 375, en dan ook Ik. Op een smal scherm hoort een schermlezer het aantal taken alleen in de naam van de balk.
- Een werkblad op een telefoon schuift zijwaarts, en de eerste kolom van de tabel blijft daarbij niet staan. Afsluiten brengt de tabel op een smal scherm terug tot Periode, Stand en Bedrag. Het zwakke punt blijft.
- De rij Eindrapport staat er vanaf afgerond. Het rapport van een lopende opdracht opent ook zonder rij, voor wie het geld leest, via Begroting en Jaarverantwoording.
- Het bord telt een vacature zonder begrotingsregel niet meer als open rol, en de FTE van een rol met een vacature is het open deel van de regel. In de voorbeeldgegevens gaat het getal daardoor van 6 naar 5. Het rapport Open rollen vervalt.
- De kolom `realised` in de downloads heet `realised_effort`, naar het woord Gerealiseerde inzet.
- Nieuw in de API: de rijen van een opdracht en een vacature (`/api/assignments/{id}/parts`, `/api/vacancies/{id}/parts`), Start (`/api/start`), zoeken (`/api/search`) en de weergaven van Mensen (`/api/people/views`). `/api/overview` blijft, als bron van Lopende opdrachten.
- ADR 0033 en 0042 zijn vervangen. ADR 0039 en 0044 zijn bijgesteld: Afsluiten en factureren is een onderdeel dat op een interne opdracht en zonder het geld Afsluiten heet, en het verloop is één regel. De regels voor een scherm staan in `docs/ontwerp.md`.
- Een hoofd zonder rechten op personen of op het geld van alle opdrachten krijgt op Start geen blok met bezetting of geld, en geen tegel die 0% zegt. Of een hoofd de bezetting als totaal zonder namen krijgt, is niet beslist; zie `docs/openstaand.md`.
- Niemand die het werk doet heeft dit getoetst. De frequenties zijn afgeleid en de persona's zijn verzonnen. Of mensen vaker landen of vaker wisselen weet niemand, en dat beslist of de wisselbalk nodig blijft. De vragen staan in `docs/openstaand.md`.

## Later gewijzigd (2026-11-28)

Na de eerste blik van de opdrachtgever (ADR 0059): Taken staat weer in de balk, direct na Start, met het aantal taken. Een taak brengt je naar de pagina en opent daar geen paneel; de stap zet je met de knop. Een opdracht toont haar verloop weer als stappenbalk in plaats van in één regel tekst. Nieuw op Start toont de laatste vijf berichten als tijdlijn per dag, en Wat is er gebeurd kan filteren op opdracht en op persoon. Alle tekst die grip zelf schrijft staat in de gewone kleur. "Wat vraagt aandacht" blijft weg.
