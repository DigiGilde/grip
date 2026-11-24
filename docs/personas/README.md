# Personaboek

Wie werkt met grip, wat die persoon in het werk moet doen, en wat grip daarvoor biedt of nog niet biedt. Elke persona heeft een vaste code, zodat documentatie, ADR's, taken en tests naar dezelfde persoon kunnen wijzen.

De personas zijn verzonnen. De organisaties zijn een spiegel van hoe de Rijksoverheid echt is ingericht, met verzonnen namen. Wetten, regelingen, fiches en functiegroepen zijn echt en staan met een bron onderaan. Echte personen worden nooit genoemd.

## Een persona noemen

- Gebruik de code als linktekst: `[PRG-PO](personas/PRG-PO.md)` vanuit `docs/`, `[PRG-PO](../personas/PRG-PO.md)` vanuit `docs/adr/`.
- In code, tests en issues noem je alleen de code: "persona PRG-PO".
- Een code wordt nooit hergebruikt of hernoemd. Valt een persona af, dan blijft het bestand staan met bovenaan waarom.
- De code bestaat uit de plek en de rol: `MIN` het Voorbeeldministerie, `PRG` het Voorbeeldprogramma, `GLD` DigiGilde voorbeeld, `ODI` Rijksorganisatie Voorbeeld ODI, het agentschap waar DigiGilde onder valt, `BHO` de Voorbeeldbeheerorganisatie.

Elk bestand begint met vaste gegevens (front matter): code, naam, rol, organisatie, eenheid, de functiegroep uit het Functiegebouw Rijk, het mandaat en per grip de toegang, de rechten in grip, de relaties en de persoon uit een voorbeelddataset. Daarna volgen dezelfde koppen in dezelfde volgorde: Wie, Verantwoordelijk voor, Mandaat en handtekening, Wat die nodig heeft, Ritme, In Grip, Wat Grip nog niet kan, Bronnen.

## De organisaties

De boom volgt het patroon van een echt ministerie met een directoraat-generaal voor digitalisering, een directie die programma's uitvoert, een CIO-directie, een agentschap met een gilde van experts en een agentschap voor beheer. Het patroon komt uit het register [organisaties.overheid.nl](https://organisaties.overheid.nl). De namen zijn verzonnen.

```
Voorbeeldministerie                                     grip: Voorbeeldministerie (instantie B)
├── SG Voorbeeldministerie
├── Directie Financieel-Economische Zaken Voorbeeld     plaats in de boom: aanname
├── DG Voorbeeld Digitalisering
│   ├── Directie CIO Voorbeeld
│   └── Directie Voorbeeld Digitale Overheid
│       └── Voorbeeldprogramma                          grip: Voorbeeldprogramma (instantie D)
│           ├── Dienst Voorbeeld Aanmelden
│           ├── Dienst Voorbeeld Berichten
│           └── Dienst Voorbeeld Machtigen
├── Rijksorganisatie Voorbeeld ODI (agentschap)         grip: bestaat nog niet (moederinstantie)
│   ├── Algemeen directeur
│   ├── Directie Bedrijfsvoering ODI
│   └── Directie Digitalisering ODI
│       └── DigiGilde voorbeeld                         grip: DigiGilde voorbeeld (instantie A)
└── Voorbeeldbeheerorganisatie (agentschap)             geen eigen grip
```

- Een dienst bestaat nog niet als begrip in grip. De drie diensten staan hier omdat het werk van een programma zo is ingedeeld.
- In de dataset `voorbeeld` heet de eigen organisatie van DigiGilde "Voorbeeldgilde". Het is hetzelfde onderdeel.
- De agentschappen hangen onder het ministerie, zoals in het echt. De Regeling agentschappen 2024 noemt de rollen: de continuïteitsverantwoordelijke (de SG of plv-SG), de beleidsverantwoordelijke (een DG of directeur die producten afneemt) en de eindverantwoordelijke (de leiding van het agentschap). In oudere stukken heet dit de driehoek eigenaar, opdrachtgever, opdrachtnemer.
- Het Rijk is een rechtspersoon, de Staat. Tussen onderdelen is er geen contract, wel een "controleerbaar vastgelegde afspraak", bijvoorbeeld een schriftelijke opdracht met een opdrachtbevestiging (Fiche verplichtingenbeheer). In grip is dat de offerte met het akkoord.

## Alle personas

| Code | Naam | Organisatie | Rol | Grips |
|---|---|---|---|---|
| [MIN-DG](MIN-DG.md) | Dorien Digitalisering | Voorbeeldministerie | Directeur-generaal, beleidsverantwoordelijke | Voorbeeldministerie |
| [MIN-DIR](MIN-DIR.md) | Tess Teken | Voorbeeldministerie | Directeur, budgethouder | Voorbeeldministerie; DigiGilde voorbeeld als gast |
| [MIN-BEL](MIN-BEL.md) | Anouk Aanvraag | Voorbeeldministerie | Senior beleidsmedewerker, opdrachtgever namens de directie | Voorbeeldministerie; Voorbeeldprogramma en DigiGilde voorbeeld via federatie |
| [MIN-FEZ](MIN-FEZ.md) | Coen Controle | Voorbeeldministerie | Controller FEZ | Voorbeeldministerie |
| [MIN-ADM](MIN-ADM.md) | Astrid Administratie | Voorbeeldministerie | Medewerker financiële administratie, prestatieverklaarder | Voorbeeldministerie |
| [MIN-CIO](MIN-CIO.md) | Ivo Informatie | Voorbeeldministerie | Adviseur CIO-office | Voorbeeldministerie |
| [PRG-DIR](PRG-DIR.md) | Mila Programma | Voorbeeldprogramma | Programmadirecteur | Voorbeeldprogramma; DigiGilde voorbeeld en Voorbeeldministerie via federatie |
| [PRG-MGR](PRG-MGR.md) | Mark Manager | Voorbeeldprogramma | Programmamanager | Voorbeeldprogramma |
| [PRG-CTRL](PRG-CTRL.md) | Fenna Financien | Voorbeeldprogramma | Programmacontroller, ondersteunt de budgethouder | Voorbeeldprogramma; DigiGilde voorbeeld via federatie |
| [PRG-SEC](PRG-SEC.md) | Sanne Secretariaat | Voorbeeldprogramma | Secretaris en PMO | Voorbeeldprogramma |
| [PRG-PO](PRG-PO.md) | Pieter Product | Voorbeeldprogramma | Product owner van een dienst | Voorbeeldprogramma |
| [PRG-TEAM](PRG-TEAM.md) | Dirk Dienstverlening | Voorbeeldprogramma | Teamlid van een dienst | Voorbeeldprogramma |
| [PRG-BEH](PRG-BEH.md) | Bram Beheer | Voorbeeldprogramma | Beheerder van de grip van het programma | Voorbeeldprogramma |
| [GLD-MGR](GLD-MGR.md) | Dana Directie | DigiGilde voorbeeld | Hoofd DigiGilde | DigiGilde voorbeeld |
| [GLD-ACC](GLD-ACC.md) | Lars Lezer | DigiGilde voorbeeld | Accountmanager | DigiGilde voorbeeld; Voorbeeldprogramma via federatie |
| [GLD-EIG](GLD-EIG.md) | Priya Product | DigiGilde voorbeeld | Opdrachteigenaar en opdrachtmanager | DigiGilde voorbeeld; Voorbeeldprogramma via federatie |
| [GLD-PLAN](GLD-PLAN.md) | Pim Planner | DigiGilde voorbeeld | Planner en teamleider | DigiGilde voorbeeld |
| [GLD-VAK](GLD-VAK.md) | Lotte Leiding | DigiGilde voorbeeld | Vakgroepleider, leidinggevende | DigiGilde voorbeeld |
| [GLD-DEV](GLD-DEV.md) | Daan Developer | DigiGilde voorbeeld | Ontwikkelaar | DigiGilde voorbeeld |
| [GLD-GOED](GLD-GOED.md) | Sem Senior | DigiGilde voorbeeld | Senior adviseur, interne goedkeurder van offertes | DigiGilde voorbeeld |
| [GLD-BEH](GLD-BEH.md) | Bente Beheer | DigiGilde voorbeeld | Beheerder van de grip van het gilde | DigiGilde voorbeeld |
| [ODI-AD](ODI-AD.md) | Arjan Agentschap | Rijksorganisatie Voorbeeld ODI | Algemeen directeur, eindverantwoordelijke | ODI als moederinstantie (bestaat nog niet); DigiGilde voorbeeld via federatie |
| [ODI-DIG](ODI-DIG.md) | Dilara Digitaal | Rijksorganisatie Voorbeeld ODI | Directeur digitalisering, directeur van het hoofd van het gilde | ODI als moederinstantie (bestaat nog niet); DigiGilde voorbeeld via federatie |
| [ODI-BV](ODI-BV.md) | Bas Bedrijfsvoering | Rijksorganisatie Voorbeeld ODI | Directeur bedrijfsvoering | ODI als moederinstantie (bestaat nog niet); DigiGilde voorbeeld via federatie |
| [ODI-BC](ODI-BC.md) | Bo Begroting | Rijksorganisatie Voorbeeld ODI | Business controller | ODI als moederinstantie (bestaat nog niet); DigiGilde voorbeeld via federatie |
| [BHO-SVC](BHO-SVC.md) | Stijn Service | Voorbeeldbeheerorganisatie | Servicemanager | geen |
| [BHO-PM](BHO-PM.md) | Pepijn Portfolio | Voorbeeldbeheerorganisatie | Productmanager | DigiGilde voorbeeld als gast |

## Wat ze in grip doen

Per persona wat die met de eigen rechten en relaties in grip doet. "nog niet" betekent dat het werk van de persona het vraagt en grip het niet biedt; "nee" dat het niet bij het werk hoort.

| Code | Aanvragen | Begroten | Offerte maken | Offerte goedkeuren | Tekenen | Inzet plannen | Werven | Maand afsluiten | Aanleveren en factuur | Uitputting inzien | Rapportage | Overleg | Beheer |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MIN-DG | nee | nee | nee | nee | nog niet | nee | nee | nee | nee | nog niet | nog niet | nog niet | nee |
| MIN-DIR | nee | nee | nee | nee | ja, en als gast | nee | nee | nee | nee | via tegenpartij | nog niet | nog niet | nee |
| MIN-BEL | ja | nee | nee | nee | nee | nee | nee | nee | nee | via tegenpartij | nog niet | nog niet | nee |
| MIN-FEZ | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nog niet | nog niet | nee | nee |
| MIN-ADM | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nog niet | nee | nee | nee |
| MIN-CIO | nee | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nog niet | nee | nee |
| PRG-DIR | ja | eigen opdrachten | eigen opdrachten | nee | ja | eigen opdrachten | eigen opdrachten | eigen opdrachten | eigen opdrachten | ja, en via tegenpartij | ja | nog niet | nee |
| PRG-MGR | nee | nee | nee | nee | nee | nee | nee | nee | nee | ja | ja | nog niet | nee |
| PRG-CTRL | nee | eigen opdrachten | eigen opdrachten | nee | nee | ja | ja | eigen opdrachten | eigen opdrachten | ja | ja | nog niet | nee |
| PRG-SEC | nee | nee | nee | nee | nee | nee | nee | nee | nee | ja | ja | nog niet | nee |
| PRG-PO | nee | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nog niet | nog niet | nee |
| PRG-TEAM | nee | nee | nee | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nee |
| PRG-BEH | nee | nee | nee | nee | nee | nee | ja | heropenen | factuur vastleggen | ja | ja | nee | ja |
| GLD-MGR | nee | nee | nee | ja | nee | nee | akkoord | nee | nee | ja | ja | nog niet | nee |
| GLD-ACC | ziet ze binnenkomen | nee | nee | nee | nee | nee | nee | nee | nee | ja | ja | nog niet | nee |
| GLD-EIG | nee | eigen opdrachten | eigen opdrachten | nee | nee | eigen opdrachten | eigen opdrachten | eigen opdrachten | eigen opdrachten | eigen opdrachten | eigen opdrachten | nog niet | nee |
| GLD-PLAN | nee | eigen opdrachten | eigen opdrachten | nee | nee | ja | ja | eigen opdrachten | eigen opdrachten | eigen opdrachten | eigen opdrachten | nee | nee |
| GLD-VAK | nee | eigen opdrachten | eigen opdrachten | nee | nee | eigen opdrachten | eigen opdrachten | eigen opdrachten | eigen opdrachten | eigen opdrachten | eigen opdrachten | nee | nee |
| GLD-DEV | nee | nee | nee | nee | nee | nee | nee | nee | nee | nee | nee | nee | nee |
| GLD-GOED | nee | nee | nee | ja | nee | nee | nee | nee | nee | nee | nee | nee | nee |
| GLD-BEH | nee | nee | nee | nee | nee | nee | ja | heropenen | factuur vastleggen | ja | ja | nee | ja |
| ODI-AD | nee | nee | nee | nee | nee | nee | nee | nee | nee | via doorgifte | nog niet | nog niet | nee |
| ODI-DIG | nee | nee | nee | nee | nee | nee | nee | nee | nee | via doorgifte | nog niet | nog niet | nee |
| ODI-BV | nee | nee | nee | nee | nee | nee | nee | nee | nee | via doorgifte | nog niet | nog niet | nee |
| ODI-BC | nee | nee | nee | nee | nee | nee | nee | nee | nee | via doorgifte | nog niet | nog niet | nee |
| BHO-SVC | nee | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nee | nog niet | nee |
| BHO-PM | nog niet | nee | nee | nee | als gast | nee | nee | nee | nee | nog niet | nee | nog niet | nee |

- **Aanvragen** is het recht aanvrager: een offerte vragen aan een gekoppelde grip. Een opdrachtnemer ziet een aanvraag binnenkomen als een potentiële opdracht.
- **Begroten, offerte maken, maand afsluiten, aanleveren** doet alleen de eigenaar of een manager van een opdracht, ook de beheerder niet.
- **Offerte goedkeuren** is de interne goedkeuring voor een offerte de deur uitgaat, alleen als de instantie die aanzet. Wie de offerte maakte, keurt haar niet goed (ADR 0048).
- **Werven**: een vacature maken en aanvragen doet de beheerder, een planner, of de eigenaar of een manager van de opdracht waar de rol bij hoort. Advies en akkoord geeft wie op de vacature is genoemd.
- **Tekenen** is het akkoord van de opdrachtgever: met het recht tekenbevoegde in de eigen grip, of als gast met een tekenlink in de grip van de opdrachtnemer.
- **Uitputting via tegenpartij** betekent: de opdrachtgever vraagt de uitputting op bij de grip van de opdrachtnemer, als die dat in de koppeling toestaat.
- **Overleg** bestaat nog niet in grip. De kolom staat er omdat bijna elke persona er tijd in steekt.

## Personas in meer grips

Een persona kan op drie manieren met een grip te maken hebben. Met een **account** is zij een persoon in die instantie. Als **gast** heeft zij geen account en tekent zij één offerte via een tekenlink. **Via federatie** komt zij nooit in de andere grip: haar eigen grip haalt gegevens op of krijgt ze toegestuurd, via FSC.

| Code | Eigen grip | Elders | Hoe |
|---|---|---|---|
| MIN-DIR | Voorbeeldministerie, tekenbevoegde | DigiGilde voorbeeld | Als gast: een offerte die het gilde met een tekenlink aanbiedt, zoals Opdracht Delta 2026-2027 in de dataset `voorbeeld` |
| MIN-BEL | Voorbeeldministerie, aanvrager | Voorbeeldprogramma, DigiGilde voorbeeld | Via federatie: zij volgt de stand en vraagt de uitputting op |
| PRG-DIR | Voorbeeldprogramma, aanvrager en tekenbevoegde | DigiGilde voorbeeld, Voorbeeldministerie | Via federatie: aanvraag en akkoord naar het gilde, de jaarofferte van het programma naar het ministerie |
| PRG-CTRL | Voorbeeldprogramma, planner en lezer | DigiGilde voorbeeld | Via federatie: een kostenpost die het gilde uitvoert; het programma houdt een verwijzing en leest omschrijving, bedrag en factuurregels bij het gilde (ADR 0052, 0053) |
| GLD-ACC | DigiGilde voorbeeld, lezer | Voorbeeldprogramma | Via federatie: de aanvraag van het programma komt binnen als potentiële opdracht. Zij tekent niets |
| GLD-EIG | DigiGilde voorbeeld, eigenaar | Voorbeeldprogramma | Via federatie: de offerte gaat via de grip van het programma, het akkoord komt terug |
| BHO-PM | geen | DigiGilde voorbeeld | Als gast: tekent een offerte van het gilde met een tekenlink |
| ODI-AD, ODI-DIG, ODI-BV, ODI-BC | ODI als moederinstantie (bestaat nog niet) | DigiGilde voorbeeld | Via federatie: de moeder haalt op wat het gilde doorgeeft (opdrachten, factuurgegevens, bezetting en capaciteit als aantallen, kosten met overhead en dekking). Geen van de vier heeft een account in een bestaande instantie |
| BHO-SVC | geen | geen | De Voorbeeldbeheerorganisatie staat als organisatie in de grip van het programma; de servicemanager zelf komt in geen grip |

## Voorbeeldpersonen uit de datasets

De personen uit de datasets blijven bestaan en zijn aan een persona gekoppeld. Wie nog ontbreekt, komt er later bij.

- Dataset `voorbeeld` (DigiGilde voorbeeld): Bente Beheer (GLD-BEH), Pim Planner (GLD-PLAN), Lotte Leiding (GLD-VAK), Dana Directie (GLD-MGR), Lars Lezer (GLD-ACC), Priya Product (GLD-EIG), Daan Developer (GLD-DEV), Sem Senior (GLD-GOED). Dewi Developer, Olaf Ontwerp en Anna Analist zijn ook GLD-DEV; Ilse Inhuur is een ingehuurd teamlid zonder eigen persona.
- Dataset `programma` (Voorbeeldprogramma): Bram Beheer (PRG-BEH), Mila Programma (PRG-DIR), Fenna Financien (PRG-CTRL), Pieter Product (PRG-PO), Dirk Dienstverlening (PRG-TEAM). Chantal Communicatie is ook PRG-TEAM.
- **Anouk Aanvraag en Tess Teken** staan in de dataset `voorbeeld`, met alleen een recht aan de kant van de opdrachtgever en zonder inzetschaal. Ze spelen daar binnen één instantie de opdrachtgever na, zodat de hele reis van aanvraag tot akkoord in één grip te zien is. Het personaboek koppelt ze aan MIN-BEL en MIN-DIR, de personen die dat werk in het echt in de grip van het ministerie doen. Hun gegevens in het personaboek noemen de dataset `voorbeeld`, ook al hoort de persona bij de grip van het ministerie.
- Voor het Voorbeeldministerie is er nog geen dataset. MIN-DG, MIN-FEZ, MIN-ADM en MIN-CIO hebben daarom geen voorbeeldpersoon.

Waar de persona afwijkt van de dataset:

| Code | Persoon | Verschil |
|---|---|---|
| GLD-MGR | Dana Directie | De naam wijst op een directie, de rol is hoofd van het gilde en geen directeur. In de dataset heeft zij geen recht in grip en geeft zij akkoord op vacatures. De persona heeft ook lezer en interne goedkeurder van offertes |
| GLD-ACC | Lars Lezer | In de dataset schaal 11; een accountmanager zit hoger. Het recht lezer klopt |
| PRG-DIR | Mila Programma | In de dataset heet haar functie programmamanager. De persona is programmadirecteur; haar rechten zijn dezelfde |
| PRG-MGR | geen | Het programma heeft in de dataset geen programmamanager; Mila Programma heeft daar die functienaam |
| PRG-SEC | geen | Het programma heeft in de dataset geen secretaris |

## Andere keuzes

- **Zevenentwintig personas.** De lijst volgt de rollen die in het werk van een programma, een ministerie, een gilde en een beheerorganisatie voorkomen. Wie in grip hetzelfde doet en in het werk ook, is een persona: de vier ontwikkelaars, de ontwerper en de analist uit de dataset zijn samen GLD-DEV.
- **De accountmanager is lezer.** Een binnenkomende aanvraag is te zien voor wie klasse A van alle opdrachten leest. Dat is het recht lezer, en een accountmanager wil ook de potentiële opdrachten en de totalen zien.
- **Het hoofd van het gilde tekent in grip niet.** Een opdrachtnemer tekent in grip niets: het akkoord is van de opdrachtgever. Haar handtekening staat als naam in het tekenblok van de offerte (Beheer, Afzender en teksten van offertes). Wat grip haar wel geeft, is de interne goedkeuring.
- **Het budget van het programma is een opdracht.** In de dataset `programma` is het jaarbudget de opdracht "Voorbeeldprogramma 2026" van het ministerie, met een offerte en een akkoord. In het echt is het een toedeling uit de begroting van de directie. ADR 0052 zegt dat een budget op het niveau van een programma nog niet bestaat.

## Wat Grip nog niet kan

Per gat de personas die het raken. Geplande onderdelen staan bovenaan.

| Gat | Wat het is | Personas |
|---|---|---|
| Diensten | Een programma deelt zijn werk in naar diensten. Gepland: een dienst als begrip, kosten naar rato over diensten verdeeld, standaard naar het aandeel directe kosten en met de hand aan te passen, en een aandeel per lidmaatschap van een persoon. Wie bij een dienst hoort zonder bekend aandeel (de programmamanager), draagt via de algemene verdeelsleutel bij. Er is ook geen rol tussen de programmadirecteur en de dienst | PRG-PO, PRG-TEAM, PRG-DIR, PRG-MGR, PRG-CTRL, MIN-BEL, BHO-SVC |
| Overleg | Gepland: reeksen van overleggen, besluiten en acties als taken die op één plek leven en die de opdrachtgever via federatie kan zien en volgen, een verslag vaststellen, een export naar het DMS, en wat de Woo en de Archiefwet vragen | PRG-SEC, PRG-DIR, PRG-MGR, PRG-PO, PRG-TEAM, MIN-DG, MIN-DIR, MIN-BEL, GLD-MGR, GLD-ACC, GLD-EIG, BHO-SVC, BHO-PM |
| Prestatieverklaring | Aan de kant van de opdrachtgever bevestigt iemand dat geleverd is wat gefactureerd wordt (hoeveelheid, prijs, kwaliteit), met naam, functie, datum en bewijs, en in principe niet wie de opdracht gaf | MIN-ADM, MIN-FEZ, MIN-BEL, PRG-CTRL, PRG-DIR |
| Mandaatgrenzen | Een tekenbevoegdheid is ja of nee per eenheid. Grip kent geen bedrag per ondertekenaar en brengt een grote offerte niet naar wie hoger mandaat heeft. Ook de interne goedkeuring kent geen grens | MIN-DG, MIN-DIR, MIN-FEZ, PRG-DIR, GLD-MGR, GLD-GOED, BHO-PM |
| Verplichtingen met kasprognose | Een verplichting met einddatum en een kasprognose per jaar, vastgelegd voor de eerste betaling (art. 20 RFB 2026) | MIN-FEZ, MIN-ADM, MIN-DIR, PRG-CTRL |
| Budget van een programma | Een jaarbudget boven de opdrachten. Nu is het budget de begroting van één opdracht van het ministerie (ADR 0052) | PRG-DIR, PRG-CTRL, MIN-BEL, MIN-DIR, MIN-FEZ |
| Instantie voor ODI | DigiGilde geeft door aan de instantie van ODI (ADR 0016); de routes bestaan met tests, maar er is geen voorbeeldinstantie voor ODI en geen scherm voor de moeder | ODI-AD, ODI-DIG, ODI-BV, ODI-BC, GLD-MGR, GLD-BEH |
| Tertaalrapportage | ODI rapporteert per tertaal aan het ministerie. Rapportage in grip staat per jaar (steering, jaarverantwoording); een stand per tertaal ontbreekt | ODI-AD, ODI-DIG, ODI-BV, ODI-BC, GLD-MGR |
| Afstemmen met bedrijfsvoering | De financiële cijfers voor de rapportage worden buiten grip naast de administratie van ODI gelegd. Grip kent geen vastgestelde stand per moment, geen gedeeld overzicht voor het gilde en bedrijfsvoering en geen plek voor een verschil met de reden | ODI-DIG, ODI-BV, ODI-BC, GLD-MGR |
| Dataset voor het Voorbeeldministerie | De grip van het ministerie heeft geen eigen voorbeeldgegevens; de kant van de opdrachtgever is alleen na te spelen met Anouk Aanvraag en Tess Teken in DigiGilde voorbeeld | MIN-DG, MIN-DIR, MIN-BEL, MIN-FEZ, MIN-ADM, MIN-CIO |
| Verrekenen tussen onderdelen van het Rijk | Factuur, interne doorbelasting of budgetoverboeking: de vraag aan de financiële administratie staat open ([openstaand.md](../openstaand.md), ADR 0039) | MIN-ADM, MIN-FEZ, PRG-CTRL, GLD-EIG, GLD-BEH |
| Meekijken bij de opdrachtgever | Aanvragen staat alleen in de balk van een aanvrager en een tekenbevoegde. Voor leiding, controller en CIO-office is er geen overzicht van wat het ministerie heeft gevraagd, getekend en uitgegeven | MIN-DG, MIN-FEZ, MIN-CIO, MIN-ADM |
| Een uitvoerder zonder grip | Alleen een organisatie met een actieve koppeling kan een kostenpost uitvoeren; het programma leest haar daar (ADR 0052). Facturen van de beheerorganisatie legt het programma zelf vast | BHO-SVC, BHO-PM, PRG-CTRL |
| Verlengen of groeien na akkoord | Een aanvullende offerte op een lopende opdracht is ontworpen, niet gebouwd ([werkstromen.md](../werkstromen.md)) | GLD-EIG, GLD-ACC, PRG-DIR, MIN-DIR |
| Begrotingsmomenten van het Rijk | Geen stand per moment van de begrotingscyclus (ontwerpbegroting, Voorjaarsnota, Najaarsnota, jaarverslag), geen kasschuif | MIN-FEZ, PRG-CTRL, MIN-DIR |
| Grote ICT-activiteit en CIO-oordeel | Geen kenmerk voor een grote ICT-activiteit en geen plek voor het oordeel van de CIO | MIN-CIO, MIN-DG |
| Handtekening van de opdrachtnemer | De handtekening van het gilde is een naam op de brief, geen handeling met een bewijs | GLD-MGR, BHO-PM |
| Eigenaar van een binnengekomen aanvraag | Een aanvraag uit een andere grip komt binnen zonder eigenaar; de beheerder wijst die aan | GLD-ACC, GLD-EIG, GLD-BEH |
| Aanvragen zonder eigen grip | Een organisatie zonder grip kan geen aanvraag sturen; zij krijgt alleen een offerte als document of met een tekenlink | BHO-PM |

## Bronnen

| Bron | Waarvoor |
|---|---|
| [Regeling agentschappen 2024](https://wetten.overheid.nl/BWBR0050264/) | Continuïteitsverantwoordelijke, beleidsverantwoordelijke, eindverantwoordelijke; werkafspraken en jaarplan |
| [Mandaatbesluit BZK 2025](https://wetten.overheid.nl/BWBR0051453/) | De bedragen per functie, bijlage 1. In dit boek altijd "naar het voorbeeld van": het Voorbeeldministerie heeft geen eigen besluit |
| [Regeling financieel beheer van het Rijk 2026](https://wetten.overheid.nl/BWBR0051547/2026-07-01/0) | Controles voor betalen (art. 10), betalen tussen onderdelen (art. 12), verplichtingen met einddatum en kasprognose (art. 20 en 21) |
| [Besluit taak FEZ](https://wetten.overheid.nl/BWBR0041910/) | Wat de directie FEZ doet |
| [Besluit CIO-stelsel Rijksdienst](https://wetten.overheid.nl/BWBR0044613/) | De departementale CIO, het informatieplan, het CIO-oordeel |
| [Fiche prestatieverklaringen](https://rijksfinancien.nl/sites/default/files/hafir/fiches/Fiche-prestatieverklaringen-van-het-Rijk.pdf) | Wie verklaart dat geleverd is en wat daarbij hoort |
| [Fiche verplichtingenbeheer](https://rijksfinancien.nl/sites/default/files/hafir/fiches/Fiche-Verplichtingenbeheer-bij-het-Rijk.pdf) | Afspraken tussen onderdelen van het Rijk, factuur of budgetoverboeking |
| [Functiegebouw Rijk](https://www.functiegebouwrijksoverheid.nl/functiegebouw/functiefamilies) | Functiefamilies, functiegroepen en schalen |
| [organisaties.overheid.nl](https://organisaties.overheid.nl) | Het patroon van de organisatieboom |
| [Rijksorganisatie ODI](https://www.rijksorganisatieodi.nl) | Hoe een opdracht aan een expertpool verloopt: aanvraag, intake, voorstel, offerte, vaste tarieven |
| Logius, Stand van de uitvoering 2023 en 2024 | Knelpunten tussen opdrachtgever en opdrachtnemer |

### Bron en aanname

- **[bron]**: de bewering staat in de genoemde wet, regeling, fiche of op de genoemde pagina. In de tekst een link.
- **[aanname]**: een redelijke inschatting van hoe het werk gaat, niet uit een bron. Te toetsen bij iemand die het werk doet.
- **inschatting** bij een functiegroep: het Functiegebouw Rijk heeft geen groep die echt past (product owner, accountmanager, servicemanager, planner, beheerder). De gekozen groep ligt het dichtst bij.
- Het Functiegebouw Rijk regelt nooit het mandaat. Mandaat komt uit een mandaatbesluit.
