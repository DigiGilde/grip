# Personaboek

Wie werkt met grip, wat die persoon in het werk moet doen, en wat grip daarvoor biedt of nog niet biedt. Elke persona heeft een vaste code, zodat documentatie, ADR's, taken en tests naar dezelfde persoon kunnen wijzen.

De personas zijn verzonnen. De organisaties zijn een spiegel van hoe de Rijksoverheid echt is ingericht. Een organisatie die echt bestaat draagt haar echte naam met "voorbeeld" erachter, zoals Ministerie van BZK voorbeeld; de mensen en bedragen zijn verzonnen. De beheerorganisatie heeft een verzonnen naam. Wetten, regelingen, fiches en functiegroepen zijn echt en staan met een bron onderaan. Echte personen worden nooit genoemd.

## Een persona noemen

- Gebruik de code als linktekst: `[PRG-PO](personas/PRG-PO.md)` vanuit `docs/`, `[PRG-PO](../personas/PRG-PO.md)` vanuit `docs/adr/`.
- In code, tests en issues noem je alleen de code: "persona PRG-PO".
- Een code wordt nooit hergebruikt of hernoemd. Valt een persona af, dan blijft het bestand staan met bovenaan waarom.
- De code bestaat uit de plek en de rol: `MIN` het Ministerie van BZK voorbeeld (ook voor de beheerder: MIN-BEH, geen BZK-), `GDI` GDI voorbeeld, `PRG` MOZa voorbeeld, `ODI` ODI voorbeeld, het agentschap waar DigiGilde onder valt, `GLD` DigiGilde voorbeeld, `EZK` het Ministerie van EZK voorbeeld, `NLDD` NLDD voorbeeld, `BHO` de Voorbeeldbeheerorganisatie.

Elk bestand begint met vaste gegevens (front matter): code, naam, rol, organisatie, eenheid, de functiegroep uit het Functiegebouw Rijk, het mandaat en per grip de toegang, de rechten in grip, de relaties en de persoon uit een voorbeelddataset. Daarna volgen dezelfde koppen in dezelfde volgorde: Wie, Verantwoordelijk voor, Mandaat en handtekening, Wat die nodig heeft, Ritme, In Grip, Wat Grip nog niet kan, Bronnen.

## De organisaties

De boom volgt het patroon van een echt ministerie met een directoraat-generaal voor digitalisering, een directie die programma's uitvoert, een CIO-directie, een agentschap met een gilde van experts en een agentschap voor beheer. Het patroon komt uit het register [organisaties.overheid.nl](https://organisaties.overheid.nl). MOZa voorbeeld wordt, zoals het echte programma, gefinancierd uit de middelen voor de GDI; de Centrale Financiering GDI staat op de begroting van BZK. GDI voorbeeld spiegelt de Programmeringsraad GDI, die het programmeringsplan opstelt. Waar ODI, het gilde en de beheerorganisatie in de boom hangen, is een aanname. Naast BZK staat het Ministerie van EZK voorbeeld met de NLDD, de dienst die DigiGilde projecten laat doen.

```
GDI voorbeeld                                             grip: GDI voorbeeld (instantie G)
└── Programmeringsraad GDI voorbeeld                      keurt het programma goed

Ministerie van BZK voorbeeld                              grip: Ministerie van BZK voorbeeld (instantie B)
├── SG BZK voorbeeld
├── Directie Financieel-Economische Zaken BZK voorbeeld   plaats in de boom: aanname
├── DG Digitalisering en Overheid voorbeeld
│   ├── Directie CIO Rijk voorbeeld
│   └── Directie Digitale Overheid voorbeeld
│       └── MOZa voorbeeld                                grip: MOZa voorbeeld (instantie D, moeder: BZK)
│           ├── Dienst Voorbeeld Aanmelden
│           ├── Dienst Voorbeeld Berichten
│           └── Dienst Voorbeeld Machtigen
├── ODI voorbeeld (agentschap)                            grip: ODI voorbeeld (instantie O)
│   ├── Algemeen directeur
│   ├── Directie Bedrijfsvoering ODI
│   └── Directie Digitalisering ODI
│       └── DigiGilde voorbeeld                           grip: DigiGilde voorbeeld (instantie A, moeder: ODI)
└── Voorbeeldbeheerorganisatie (agentschap)               geen eigen grip

Ministerie van EZK voorbeeld                              grip: Ministerie van EZK voorbeeld (instantie Z)
├── SG EZK voorbeeld
├── Directie Financieel-Economische Zaken EZK voorbeeld   plaats in de boom: aanname
└── DG Digitaliseringsbeleid Samenleving en Overheid voorbeeld   formeel vanaf 1 januari 2027
    └── NLDD voorbeeld                                    grip: NLDD voorbeeld (instantie E, moeder: EZK)
        ├── Leiding NLDD
        ├── Bureau NLDD
        ├── Traject Fundament
        └── Traject RegelRecht
```

- GDI voorbeeld heeft in de boom geen moeder. BZK is gedelegeerd opdrachtgever namens GDI, ODI is opdrachtnemer van BZK en laat het uitvoeren door DigiGilde.
- NLDD hangt direct onder het directoraat-generaal. Geen officiële tekst zegt waar de NLDD hangt; de plaats is een aanname.
- Een dienst bestaat nog niet als begrip in grip. De drie diensten staan hier omdat het werk van een programma zo is ingedeeld.
- In de dataset `voorbeeld` heet de eigen organisatie van DigiGilde "Voorbeeldgilde". Het is hetzelfde onderdeel. Het gilde is een merk van ODI voorbeeld.
- De agentschappen hangen onder het ministerie, zoals in het echt. De Regeling agentschappen 2024 noemt de rollen: de continuïteitsverantwoordelijke (de SG of plv-SG), de beleidsverantwoordelijke (een DG of directeur die producten afneemt) en de eindverantwoordelijke (de leiding van het agentschap). In oudere stukken heet dit de driehoek eigenaar, opdrachtgever, opdrachtnemer.
- Het Rijk is een rechtspersoon, de Staat. Tussen onderdelen is er geen contract, wel een "controleerbaar vastgelegde afspraak", bijvoorbeeld een schriftelijke opdracht met een opdrachtbevestiging (Fiche verplichtingenbeheer). In grip is dat de offerte met het akkoord.

## Alle personas

| Code | Naam | Organisatie | Rol | Grips |
|---|---|---|---|---|
| [GDI-VZ](GDI-VZ.md) | Petra Programmering | GDI voorbeeld | Voorzitter van de Programmeringsraad, keurt het programma goed | GDI voorbeeld; Ministerie van BZK voorbeeld via federatie |
| [GDI-SEC](GDI-SEC.md) | Stef Stelsel | GDI voorbeeld | Secretaris van de Programmeringsraad, opdrachtgever namens GDI | GDI voorbeeld; Ministerie van BZK voorbeeld via federatie |
| [GDI-BEH](GDI-BEH.md) | Britt Beheer | GDI voorbeeld | Beheerder van de grip van GDI | GDI voorbeeld |
| [MIN-DG](MIN-DG.md) | Dorien Digitalisering | Ministerie van BZK voorbeeld | Directeur-generaal, beleidsverantwoordelijke | Ministerie van BZK voorbeeld |
| [MIN-DIR](MIN-DIR.md) | Tess Teken | Ministerie van BZK voorbeeld | Directeur, budgethouder | Ministerie van BZK voorbeeld; DigiGilde voorbeeld als gast |
| [MIN-BEL](MIN-BEL.md) | Anouk Aanvraag | Ministerie van BZK voorbeeld | Senior beleidsmedewerker, opdrachtgever namens de directie | Ministerie van BZK voorbeeld; MOZa voorbeeld en DigiGilde voorbeeld via federatie |
| [MIN-FEZ](MIN-FEZ.md) | Coen Controle | Ministerie van BZK voorbeeld | Controller FEZ | Ministerie van BZK voorbeeld |
| [MIN-ADM](MIN-ADM.md) | Astrid Administratie | Ministerie van BZK voorbeeld | Medewerker financiële administratie, prestatieverklaarder | Ministerie van BZK voorbeeld |
| [MIN-CIO](MIN-CIO.md) | Ivo Informatie | Ministerie van BZK voorbeeld | Adviseur CIO-office | Ministerie van BZK voorbeeld |
| [MIN-BEH](MIN-BEH.md) | Berend Beheer | Ministerie van BZK voorbeeld | Beheerder van de grip van het ministerie | Ministerie van BZK voorbeeld |
| [PRG-DIR](PRG-DIR.md) | Mila Programma | MOZa voorbeeld | Programmadirecteur | MOZa voorbeeld; DigiGilde voorbeeld en Ministerie van BZK voorbeeld via federatie |
| [PRG-MGR](PRG-MGR.md) | Mark Manager | MOZa voorbeeld | Programmamanager | MOZa voorbeeld |
| [PRG-CTRL](PRG-CTRL.md) | Fenna Financien | MOZa voorbeeld | Programmacontroller, ondersteunt de budgethouder | MOZa voorbeeld; DigiGilde voorbeeld via federatie |
| [PRG-SEC](PRG-SEC.md) | Sanne Secretariaat | MOZa voorbeeld | Secretaris en PMO | MOZa voorbeeld |
| [PRG-PO](PRG-PO.md) | Pieter Product | MOZa voorbeeld | Product owner van een dienst | MOZa voorbeeld |
| [PRG-TEAM](PRG-TEAM.md) | Dirk Dienstverlening | MOZa voorbeeld | Teamlid van een dienst | MOZa voorbeeld |
| [PRG-BEH](PRG-BEH.md) | Bram Beheer | MOZa voorbeeld | Beheerder van de grip van het programma | MOZa voorbeeld |
| [GLD-MGR](GLD-MGR.md) | Dana Directie | DigiGilde voorbeeld | Hoofd DigiGilde | DigiGilde voorbeeld |
| [GLD-ACC](GLD-ACC.md) | Lars Lezer | DigiGilde voorbeeld | Accountmanager | DigiGilde voorbeeld; MOZa voorbeeld via federatie |
| [GLD-EIG](GLD-EIG.md) | Priya Product | DigiGilde voorbeeld | Opdrachteigenaar en opdrachtmanager | DigiGilde voorbeeld; MOZa voorbeeld en NLDD voorbeeld via federatie |
| [GLD-PLAN](GLD-PLAN.md) | Pim Planner | DigiGilde voorbeeld | Planner en teamleider | DigiGilde voorbeeld |
| [GLD-VAK](GLD-VAK.md) | Lotte Leiding | DigiGilde voorbeeld | Vakgroepleider, leidinggevende | DigiGilde voorbeeld; NLDD voorbeeld via federatie |
| [GLD-DEV](GLD-DEV.md) | Daan Developer | DigiGilde voorbeeld | Ontwikkelaar | DigiGilde voorbeeld |
| [GLD-GOED](GLD-GOED.md) | Sem Senior | DigiGilde voorbeeld | Senior adviseur, interne goedkeurder van offertes | DigiGilde voorbeeld |
| [GLD-BEH](GLD-BEH.md) | Bente Beheer | DigiGilde voorbeeld | Beheerder van de grip van het gilde | DigiGilde voorbeeld |
| [ODI-AD](ODI-AD.md) | Arjan Agentschap | ODI voorbeeld | Algemeen directeur, eindverantwoordelijke | ODI voorbeeld; DigiGilde voorbeeld via federatie |
| [ODI-DIG](ODI-DIG.md) | Dilara Digitaal | ODI voorbeeld | Directeur digitalisering, directeur van het hoofd van het gilde | ODI voorbeeld; DigiGilde voorbeeld via federatie |
| [ODI-BV](ODI-BV.md) | Bas Bedrijfsvoering | ODI voorbeeld | Directeur bedrijfsvoering | ODI voorbeeld; DigiGilde voorbeeld via federatie |
| [ODI-BC](ODI-BC.md) | Bo Begroting | ODI voorbeeld | Business controller | ODI voorbeeld; DigiGilde voorbeeld via federatie |
| [ODI-BEH](ODI-BEH.md) | Benno Beheer | ODI voorbeeld | Beheerder van de grip van ODI | ODI voorbeeld |
| [EZK-DG](EZK-DG.md) | Sabine Samenleving | Ministerie van EZK voorbeeld | Directeur-generaal Digitaliseringsbeleid Samenleving en Overheid, beleidsverantwoordelijke | Ministerie van EZK voorbeeld |
| [EZK-FEZ](EZK-FEZ.md) | Mirjam Middelen | Ministerie van EZK voorbeeld | Controller FEZ | Ministerie van EZK voorbeeld |
| [EZK-BEH](EZK-BEH.md) | Babette Beheer | Ministerie van EZK voorbeeld | Beheerder van de grip van het ministerie | Ministerie van EZK voorbeeld |
| [NLDD-DIR](NLDD-DIR.md) | Daphne Dienst | NLDD voorbeeld | Directeur NLDD | NLDD voorbeeld; DigiGilde voorbeeld via federatie |
| [NLDD-TRJ](NLDD-TRJ.md) | Floor Fundament | NLDD voorbeeld | Trajectleider, opdrachtgever namens NLDD | NLDD voorbeeld; DigiGilde voorbeeld via federatie |
| [NLDD-BEH](NLDD-BEH.md) | Boris Beheer | NLDD voorbeeld | Beheerder van de grip van NLDD | NLDD voorbeeld |
| [BHO-SVC](BHO-SVC.md) | Stijn Service | Voorbeeldbeheerorganisatie | Servicemanager | geen |
| [BHO-PM](BHO-PM.md) | Pepijn Portfolio | Voorbeeldbeheerorganisatie | Productmanager | DigiGilde voorbeeld als gast |

## Wat ze in grip doen

Per persona wat die met de eigen rechten en relaties in grip doet. "nog niet" betekent dat het werk van de persona het vraagt en grip het niet biedt; "nee" dat het niet bij het werk hoort.

| Code | Aanvragen | Begroten | Offerte maken | Offerte goedkeuren | Tekenen | Inzet plannen | Werven | Maand afsluiten | Aanleveren en factuur | Uitputting inzien | Rapportage | Overleg | Beheer |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GDI-VZ | nee | nee | nee | nee | ja | nee | nee | nee | nee | via tegenpartij | nog niet | nog niet | nee |
| GDI-SEC | ja | nee | nee | nee | nee | nee | nee | nee | nee | via tegenpartij | nog niet | nog niet | nee |
| GDI-BEH | nee | nee | nee | nee | nee | nee | ja | heropenen | factuur vastleggen | ja | ja | nee | ja |
| MIN-DG | nee | nee | nee | nee | nog niet | nee | nee | nee | nee | nog niet | nog niet | nog niet | nee |
| MIN-DIR | nee | nee | nee | nee | ja, en als gast | nee | nee | nee | nee | via tegenpartij | nog niet | nog niet | nee |
| MIN-BEL | ja | nee | nee | nee | nee | nee | nee | nee | nee | via tegenpartij | nog niet | nog niet | nee |
| MIN-FEZ | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nog niet | nog niet | nee | nee |
| MIN-ADM | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nog niet | nee | nee | nee |
| MIN-CIO | nee | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nog niet | nee | nee |
| MIN-BEH | nee | nee | nee | nee | nee | nee | ja | heropenen | factuur vastleggen | ja | ja | nee | ja |
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
| ODI-BEH | nee | nee | nee | nee | nee | nee | ja | heropenen | factuur vastleggen | ja | ja | nee | ja |
| EZK-DG | nee | nee | nee | nee | nog niet | nee | nee | nee | nee | nog niet | nog niet | nog niet | nee |
| EZK-FEZ | nee | nee | nee | nee | nee | nee | nee | nee | nog niet | nog niet | nog niet | nee | nee |
| EZK-BEH | nee | nee | nee | nee | nee | nee | ja | heropenen | factuur vastleggen | ja | ja | nee | ja |
| NLDD-DIR | nee | nee | nee | nee | ja | nee | nee | nee | nee | via tegenpartij | nog niet | nog niet | nee |
| NLDD-TRJ | ja | nee | nee | nee | nee | nee | nee | nee | nee | via tegenpartij | nog niet | nog niet | nee |
| NLDD-BEH | nee | nee | nee | nee | nee | nee | ja | heropenen | factuur vastleggen | ja | ja | nee | ja |
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
| GDI-VZ | GDI voorbeeld, tekenbevoegde en lezer | Ministerie van BZK voorbeeld | Via federatie: de opdracht van GDI aan BZK (gedelegeerd opdrachtgeverschap) loopt via de koppeling |
| GDI-SEC | GDI voorbeeld, aanvrager en eigenaar | Ministerie van BZK voorbeeld | Via federatie: zij volgt de stand van de opdracht en vraagt de uitputting op |
| MIN-DIR | Ministerie van BZK voorbeeld, tekenbevoegde | DigiGilde voorbeeld | Als gast: een offerte die het gilde met een tekenlink aanbiedt, zoals Opdracht Delta 2026-2027 in de dataset `voorbeeld` |
| MIN-BEL | Ministerie van BZK voorbeeld, aanvrager | MOZa voorbeeld, DigiGilde voorbeeld | Via federatie: zij volgt de stand en vraagt de uitputting op |
| PRG-DIR | MOZa voorbeeld, aanvrager en tekenbevoegde | DigiGilde voorbeeld, Ministerie van BZK voorbeeld | Via federatie: aanvraag en akkoord naar het gilde, de jaarofferte van het programma naar het ministerie |
| PRG-CTRL | MOZa voorbeeld, planner en lezer | DigiGilde voorbeeld | Via federatie: een kostenpost die het gilde uitvoert; het programma houdt een verwijzing en leest omschrijving, bedrag en factuurregels bij het gilde (ADR 0052, 0053) |
| GLD-ACC | DigiGilde voorbeeld, lezer | MOZa voorbeeld | Via federatie: de aanvraag van het programma komt binnen als potentiële opdracht. Zij tekent niets |
| GLD-EIG | DigiGilde voorbeeld, eigenaar | MOZa voorbeeld, NLDD voorbeeld | Via federatie: de offerte gaat via de grip van de opdrachtgever, het akkoord komt terug; Fundament 2026-2027 is van NLDD |
| GLD-VAK | DigiGilde voorbeeld, eigenaar en leidinggevende | NLDD voorbeeld | Via federatie: RegelRecht 2026-2027 is van NLDD; offerte en akkoord lopen via de koppeling |
| NLDD-DIR | NLDD voorbeeld, tekenbevoegde en lezer | DigiGilde voorbeeld | Via federatie: zij tekent in de eigen grip en vraagt de stand en de uitputting op |
| NLDD-TRJ | NLDD voorbeeld, aanvrager en eigenaar | DigiGilde voorbeeld | Via federatie: aanvraag naar het gilde, offerte en uitputting terug |
| BHO-PM | geen | DigiGilde voorbeeld | Als gast: tekent een offerte van het gilde met een tekenlink |
| ODI-AD, ODI-DIG, ODI-BV, ODI-BC | ODI voorbeeld, lezer | DigiGilde voorbeeld | Via federatie: de moeder haalt op wat het gilde doorgeeft (opdrachten, factuurgegevens, bezetting en capaciteit als aantallen, kosten met overhead en dekking). Een scherm dat dat toont bestaat nog niet |
| BHO-SVC | geen | geen | De Voorbeeldbeheerorganisatie staat als organisatie in de grip van het programma; de servicemanager zelf komt in geen grip |

De beheerders (MIN-BEH, GDI-BEH, ODI-BEH, EZK-BEH, NLDD-BEH, PRG-BEH, GLD-BEH) en de overige personen met alleen een eigen grip staan niet in deze tabel. EZK-DG en EZK-FEZ komen alleen in de grip van het ministerie van EZK voorbeeld; wat NLDD doorgeeft, zien ze nog niet.

## Voorbeeldpersonen uit de datasets

De personen uit de datasets blijven bestaan en zijn aan een persona gekoppeld. Elke voorbeeldinstantie heeft een eigen dataset.

- Dataset `voorbeeld` (DigiGilde voorbeeld): Bente Beheer (GLD-BEH), Pim Planner (GLD-PLAN), Lotte Leiding (GLD-VAK), Dana Directie (GLD-MGR), Lars Lezer (GLD-ACC), Priya Product (GLD-EIG), Daan Developer (GLD-DEV), Sem Senior (GLD-GOED). Dewi Developer, Olaf Ontwerp en Anna Analist zijn ook GLD-DEV, net als Cas Cloud, Pleun Platform, Joost Jurist, Kim Kode en Erik Extern, de vijf mensen op de opdrachten van NLDD voorbeeld. Erik Extern is ingehuurd bij "Voorbeeld Detachering B.V."; Ilse Inhuur is een ingehuurd teamlid zonder eigen persona. Priya Product is eigenaar van Fundament 2026-2027, Lotte Leiding van RegelRecht 2026-2027, Pim Planner is manager van beide.
- Dataset `programma` (MOZa voorbeeld): Bram Beheer (PRG-BEH), Mila Programma (PRG-DIR), Fenna Financien (PRG-CTRL), Pieter Product (PRG-PO), Dirk Dienstverlening (PRG-TEAM). Chantal Communicatie is ook PRG-TEAM.
- Dataset `bzk` (Ministerie van BZK voorbeeld): Berend Beheer (MIN-BEH), Dorien Digitalisering (MIN-DG), Tess Teken (MIN-DIR), Anouk Aanvraag (MIN-BEL), Coen Controle (MIN-FEZ), Astrid Administratie (MIN-ADM), Ivo Informatie (MIN-CIO). Dorien Digitalisering is eigenaar van de opdracht die het ministerie van GDI kreeg, Anouk Aanvraag van de opdrachten die het ministerie geeft.
- Dataset `gdi` (GDI voorbeeld): Britt Beheer (GDI-BEH), Petra Programmering (GDI-VZ), Stef Stelsel (GDI-SEC).
- Dataset `odi` (ODI voorbeeld): Benno Beheer (ODI-BEH), Arjan Agentschap (ODI-AD), Dilara Digitaal (ODI-DIG), Bas Bedrijfsvoering (ODI-BV), Bo Begroting (ODI-BC). Dilara Digitaal is eigenaar van de opdracht die ODI van het ministerie kreeg.
- Dataset `ezk` (Ministerie van EZK voorbeeld): Babette Beheer (EZK-BEH), Sabine Samenleving (EZK-DG), Mirjam Middelen (EZK-FEZ).
- Dataset `nldd` (NLDD voorbeeld): Boris Beheer (NLDD-BEH), Daphne Dienst (NLDD-DIR), Floor Fundament (NLDD-TRJ, eigenaar van Fundament). Romy Recht is ook NLDD-TRJ en eigenaar van RegelRecht.
- **Anouk Aanvraag en Tess Teken** staan ook in de dataset `voorbeeld`, met alleen een recht aan de kant van de opdrachtgever en zonder inzetschaal. Ze spelen daar binnen één instantie de opdrachtgever na, zodat de hele reis van aanvraag tot akkoord in één grip te zien is. Hun gegevens in het personaboek noemen de dataset `bzk`, waar ze bij de grip van het ministerie horen.
- Niemand buiten DigiGilde en MOZa heeft een inzetschaal of een tarievenkaart.

Waar de persona afwijkt van de dataset:

| Code | Persoon | Verschil |
|---|---|---|
| MIN-BEL, MIN-DIR | Anouk Aanvraag, Tess Teken | Staan in twee datasets: `bzk` bij de grip van het ministerie en `voorbeeld` als naspeler van de opdrachtgever bij het gilde |
| NLDD-TRJ | Floor Fundament | De persona heeft twee voorbeeldpersonen: Floor Fundament voor Fundament en Romy Recht voor RegelRecht |
| GLD-MGR | Dana Directie | De naam wijst op een directie, de rol is hoofd van het gilde en geen directeur. In de dataset heeft zij geen recht in grip en geeft zij akkoord op vacatures. De persona heeft ook lezer en interne goedkeurder van offertes |
| GLD-ACC | Lars Lezer | In de dataset schaal 11; een accountmanager zit hoger. Het recht lezer klopt |
| PRG-DIR | Mila Programma | In de dataset heet haar functie programmamanager. De persona is programmadirecteur; haar rechten zijn dezelfde |
| PRG-MGR | geen | Het programma heeft in de dataset geen programmamanager; Mila Programma heeft daar die functienaam |
| PRG-SEC | geen | Het programma heeft in de dataset geen secretaris |

## Andere keuzes

- **Achtendertig personas.** De lijst volgt de rollen die in het werk van een programma, een ministerie, GDI, ODI, een gilde, een dienst en een beheerorganisatie voorkomen. Wie in grip hetzelfde doet en in het werk ook, is een persona: de vier ontwikkelaars, de ontwerper en de analist uit de dataset zijn samen GLD-DEV.
- **De accountmanager is lezer.** Een binnenkomende aanvraag is te zien voor wie klasse A van alle opdrachten leest. Dat is het recht lezer, en een accountmanager wil ook de potentiële opdrachten en de totalen zien.
- **Het hoofd van het gilde tekent in grip niet.** Een opdrachtnemer tekent in grip niets: het akkoord is van de opdrachtgever. Haar handtekening staat als naam in het tekenblok van de offerte (Beheer, Afzender en teksten van offertes). Wat grip haar wel geeft, is de interne goedkeuring.
- **Het budget van het programma is een opdracht.** In de dataset `programma` is het jaarbudget de opdracht "MOZa voorbeeld 2026" van het ministerie, met een offerte en een akkoord. In het echt is het een toedeling uit de begroting van de directie. ADR 0052 zegt dat een budget op het niveau van een programma nog niet bestaat.

## Wat Grip nog niet kan

Per gat de personas die het raken. Geplande onderdelen staan bovenaan. Een instantie voor ODI en een dataset voor het Ministerie van BZK voorbeeld bestaan nu; wat open is, staat hieronder.

| Gat | Wat het is | Personas |
|---|---|---|
| Diensten | Een programma deelt zijn werk in naar diensten. Gepland: een dienst als begrip, kosten naar rato over diensten verdeeld, standaard naar het aandeel directe kosten en met de hand aan te passen, en een aandeel per lidmaatschap van een persoon. Wie bij een dienst hoort zonder bekend aandeel (de programmamanager), draagt via de algemene verdeelsleutel bij. Er is ook geen rol tussen de programmadirecteur en de dienst | PRG-PO, PRG-TEAM, PRG-DIR, PRG-MGR, PRG-CTRL, MIN-BEL, BHO-SVC |
| Overleg | Gepland: reeksen van overleggen, besluiten en acties als taken die op één plek leven en die de opdrachtgever via federatie kan zien en volgen, een verslag vaststellen, een export naar het DMS, en wat de Woo en de Archiefwet vragen | PRG-SEC, PRG-DIR, PRG-MGR, PRG-PO, PRG-TEAM, MIN-DG, MIN-DIR, MIN-BEL, GLD-MGR, GLD-ACC, GLD-EIG, BHO-SVC, BHO-PM |
| Prestatieverklaring | Aan de kant van de opdrachtgever bevestigt iemand dat geleverd is wat gefactureerd wordt (hoeveelheid, prijs, kwaliteit), met naam, functie, datum en bewijs, en in principe niet wie de opdracht gaf | MIN-ADM, MIN-FEZ, MIN-BEL, PRG-CTRL, PRG-DIR |
| Mandaatgrenzen | Een tekenbevoegdheid is ja of nee per eenheid. Grip kent geen bedrag per ondertekenaar en brengt een grote offerte niet naar wie hoger mandaat heeft. Ook de interne goedkeuring kent geen grens | MIN-DG, MIN-DIR, MIN-FEZ, PRG-DIR, GLD-MGR, GLD-GOED, BHO-PM |
| Verplichtingen met kasprognose | Een verplichting met einddatum en een kasprognose per jaar, vastgelegd voor de eerste betaling (art. 20 RFB 2026) | MIN-FEZ, MIN-ADM, MIN-DIR, PRG-CTRL |
| Budget van een programma | Een jaarbudget boven de opdrachten. Nu is het budget de begroting van één opdracht van het ministerie (ADR 0052) | PRG-DIR, PRG-CTRL, MIN-BEL, MIN-DIR, MIN-FEZ |
| Een scherm voor een moederinstantie | ODI voorbeeld, het Ministerie van BZK voorbeeld en het Ministerie van EZK voorbeeld bestaan als instantie met eigen personen en opdrachten. Een scherm dat toont wat een dochter doorgeeft (DigiGilde aan ODI, MOZa aan BZK, NLDD aan EZK) bestaat niet; de doorgifte (ADR 0016) is een route | ODI-AD, ODI-DIG, ODI-BV, ODI-BC, ODI-BEH, MIN-BEH, EZK-DG, EZK-FEZ, EZK-BEH, NLDD-BEH, GLD-MGR, GLD-BEH |
| Tertaalrapportage | ODI rapporteert per tertaal aan het ministerie. Rapportage in grip staat per jaar (steering, jaarverantwoording); een stand per tertaal ontbreekt | ODI-AD, ODI-DIG, ODI-BV, ODI-BC, GLD-MGR |
| Afstemmen met bedrijfsvoering | De financiële cijfers voor de rapportage worden buiten grip naast de administratie van ODI gelegd. Grip kent geen vastgestelde stand per moment, geen gedeeld overzicht voor het gilde en bedrijfsvoering en geen plek voor een verschil met de reden | ODI-DIG, ODI-BV, ODI-BC, GLD-MGR |
| Volgen | Een opdrachtgever of moeder volgt opdrachten van een andere instantie, bijvoorbeeld NLDD die MOZa volgt, of GDI en BZK die meelezen op het programma. Het is niet gebouwd | NLDD-DIR, NLDD-TRJ, GDI-VZ, GDI-SEC, MIN-BEL, MIN-DG |
| Namen naar een opdrachtgever | Wie aan een opdracht werkt, gaat alleen mee naar de opdrachtgever als de opdrachtnemer dat per koppeling aanzet. NLDD ziet nu de stand en de uitputting, niet wie eraan werkt | NLDD-DIR, NLDD-TRJ, GLD-BEH, GLD-EIG |
| Verantwoording aan EZK | NLDD legt in grip geen verantwoording af aan het directoraat-generaal of het ministerie, en er is geen budget van de dienst | NLDD-DIR, EZK-DG, EZK-FEZ, EZK-BEH |
| Een goedgekeurd programma | GDI keurt een programma goed en delegeert het opdrachtgeverschap. Grip kent dat begrip niet; een opdracht van GDI aan BZK staat ervoor | GDI-VZ, GDI-SEC |
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
| [Mandaatbesluit BZK 2025](https://wetten.overheid.nl/BWBR0051453/) | De bedragen per functie, bijlage 1. In dit boek altijd "naar het voorbeeld van": het Ministerie van BZK voorbeeld heeft geen eigen besluit |
| [Regeling financieel beheer van het Rijk 2026](https://wetten.overheid.nl/BWBR0051547/2026-07-01/0) | Controles voor betalen (art. 10), betalen tussen onderdelen (art. 12), verplichtingen met einddatum en kasprognose (art. 20 en 21) |
| [Besluit taak FEZ](https://wetten.overheid.nl/BWBR0041910/) | Wat de directie FEZ doet |
| [Besluit CIO-stelsel Rijksdienst](https://wetten.overheid.nl/BWBR0044613/) | De departementale CIO, het informatieplan, het CIO-oordeel |
| [Fiche prestatieverklaringen](https://rijksfinancien.nl/sites/default/files/hafir/fiches/Fiche-prestatieverklaringen-van-het-Rijk.pdf) | Wie verklaart dat geleverd is en wat daarbij hoort |
| [Fiche verplichtingenbeheer](https://rijksfinancien.nl/sites/default/files/hafir/fiches/Fiche-Verplichtingenbeheer-bij-het-Rijk.pdf) | Afspraken tussen onderdelen van het Rijk, factuur of budgetoverboeking |
| [Functiegebouw Rijk](https://www.functiegebouwrijksoverheid.nl/functiegebouw/functiefamilies) | Functiefamilies, functiegroepen en schalen |
| [organisaties.overheid.nl](https://organisaties.overheid.nl) | Het patroon van de organisatieboom |
| [Instellingsbesluit Programmeringsraad GDI](https://zoek.officielebekendmakingen.nl/stcrt-2022-18861.pdf) | Taken van de Programmeringsraad GDI: advies en het jaarlijkse programmeringsplan |
| [Digitale Dienst](https://digitaledienst.overheid.nl/) | De NLDD en haar plaats onder het directoraat-generaal |
| [Rijksorganisatie ODI](https://www.rijksorganisatieodi.nl) | Hoe een opdracht aan een expertpool verloopt: aanvraag, intake, voorstel, offerte, vaste tarieven |
| Logius, Stand van de uitvoering 2023 en 2024 | Knelpunten tussen opdrachtgever en opdrachtnemer |

### Bron en aanname

- **[bron]**: de bewering staat in de genoemde wet, regeling, fiche of op de genoemde pagina. In de tekst een link.
- **[aanname]**: een redelijke inschatting van hoe het werk gaat, niet uit een bron. Te toetsen bij iemand die het werk doet.
- **inschatting** bij een functiegroep: het Functiegebouw Rijk heeft geen groep die echt past (product owner, accountmanager, servicemanager, planner, beheerder). De gekozen groep ligt het dichtst bij.
- Het Functiegebouw Rijk regelt nooit het mandaat. Mandaat komt uit een mandaatbesluit.
