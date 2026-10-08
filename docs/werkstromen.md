# Werkstromen

Een opdracht, een vacature, een tekst en een factuurperiode leggen elk een weg af waar meer mensen aan werken. Dit document zegt welke wegen dat zijn, wat een scherm daarover altijd op dezelfde plek zegt, en met welke praktijkgevallen het wordt getoetst. Het besluit staat in [ADR 0044](adr/0044-een-verloop-per-zaak-uit-dezelfde-feiten-als-de-taken.md); hoe taken werken staat in [taken.md](taken.md).

## De vier eisen

Waar ze botsen geldt deze volgorde.

1. **Eenvoudig voor wie achter het scherm zit.** Die ziet de zaak, een zin over wat er nu gebeurt en een knop. Op het scherm staat geen woord van het systeem: geen werkstroom, sjabloon, feit of planversie.
2. **Visuele hiërarchie** is hoe die eenvoud wordt geleverd: eerst wat nu moet, dan het verloop, dan het werk.
3. **Buigzaam waar het werk buigt.** Een stap die niet van toepassing is ontbreekt. Een stap die al gedaan is telt, ook buiten de volgorde. Teruggaan kan altijd en heeft een naam.
4. **Flexibel in de gegevens, nooit op het scherm.** Stappen, namen, wie handelt en termijnen staan in het plan. Er is geen instelscherm.

## Praktijkgevallen

Elk verloop dient een hoofdgeval en de varianten die echt voorkomen. De rol is een rol, nooit een naam. De status zegt wat er op 9 oktober 2026 in een browser is nagelopen.

### Een opdracht winnen

**Hoofdgeval.** Een opdrachtmanager krijgt een vraag van een ministerie. Zij maakt een potentiële opdracht, begroot de rollen, maakt de offerte, laat haar zo nodig intern goedkeuren en biedt haar aan. De opdrachtgever tekent. Zij zet de opdracht in uitvoering. Begint op: Start, onder Mijn taken, of Opdrachten.

| Variant | Wat het verloop toont | Wie is aan zet | Terug op het hoofdpad | Status |
|---|---|---|---|---|
| Hoofdgeval | Begroting, Offerte, Aanbieden, Akkoord; daarna Akkoord, Starten, Uitvoeren, Verantwoorden | eigenaar; bij Akkoord de opdrachtgever | n.v.t. | nagelopen, werkt |
| De begroting wijzigt na de offerte | Offerte is weer de huidige stap | eigenaar: "Maak een nieuwe offerte" | de nieuwe offerte vervangt de oude | nagelopen, werkt |
| De offerte verloopt | Offerte is weer de huidige stap | eigenaar | een nieuwe offerte | getest, niet in de browser |
| Een directeur moet goedkeuren | extra stap Interne goedkeuring, alleen waar de instelling het vraagt | eigenaar vraagt, goedkeurder beoordeelt | na goedkeuring Aanbieden | nagelopen, werkt |
| Niemand heeft het recht om goed te keuren | de zin zegt dat en wie het kan oplossen | beheerder | recht toekennen bij Team | nagelopen, werkt |
| Intern teruggestuurd | Offerte is weer de huidige stap | wie de offerte maakte | begroting aanpassen, nieuwe offerte | getest, niet in de browser |
| Mondeling akkoord | stap Akkoord, met de zin dat het getekende akkoord nog moet | eigenaar | getekend akkoord vastleggen | nagelopen, werkt; de eigenaar leest waar het vast te leggen is en heeft hier geen knop |
| De opdrachtgever heeft geen grip | geen verschil in het verloop; aanbieden als document of met een tekenlink | eigenaar | getekende pdf vastleggen | het verloop nagelopen, het tekenen zelf niet |
| De offerte wordt afgewezen | De opdracht blijft potentieel en staat terug op Offerte; de kop zegt wie afwees, wanneer en waarom. Stoppen is een eigen besluit: "Sluit af zonder opdracht" met een reden, einde "Niet doorgegaan". Voor de opdrachtgever die afwees eindigt het verloop als Afgewezen | eigenaar | nieuwe offerte, of afsluiten zonder opdracht | nagelopen in de browser en getest |
| De eigenaar is weg | het verloop blijft; de zin noemt de eigenaar | beheerder wijst een eigenaar aan | Overzicht, eigenaar en managers | niet nagelopen |
| Werven begint voor de handtekening | de vacature heeft een eigen verloop; de opdracht hoeft niet akkoord te zijn | planner of eigenaar | n.v.t. | getest in het plan, niet in de browser |
| Een lezer kijkt mee | dezelfde stappen; de zin zegt wie aan zet is, zonder "je wacht", zonder termijn en zonder knop | niemand hier | n.v.t. | nagelopen, werkt |
| Een manager doet de stap van de eigenaar | wie de zaak beheert en niet aan zet is, ziet "Neem deze stap over"; daarna is de stap van haar en zegt een notitie op de taak van wie hij kwam | manager of beheerder | de eigenaar kan hem terugnemen | nagelopen, werkt |

### Een opdracht uitvoeren en factureren

**Hoofdgeval.** De opdracht loopt. De planner vult de rollen. De opdrachtmanager sluit elke maand af, levert per factuurperiode aan en legt de factuur vast. Aan het eind levert zij het eindrapport op. Begint op: Start, onder Mijn taken.

| Variant | Wat het verloop toont | Wie is aan zet | Status |
|---|---|---|---|
| Hoofdgeval | Uitvoeren, met de eerstvolgende taak als zin; per periode Maanden afsluiten, Aanleveren, Factuur | eigenaar of manager, planner | nagelopen: de kop, het werk van de stap op de tab en per periode wie aan zet is |
| Een maand is te laat | de termijn staat rood onder de zin | eigenaar of manager | nagelopen, werkt |
| Per kwartaal factureren, per maand afsluiten | aanleveren wordt pas gevraagd als de periode klaar is | eigenaar of manager | getest, niet in de browser |
| Promotie midden in een maand, of een correctie na aanleveren | geen eigen stap; de taak "Lever de naverrekening aan" bestaat in het plan en wacht op een gebeurtenis die nog niet wordt vastgelegd | n.v.t. | **gat**; woorden staan klaar, de taak ontstaat nog niet |
| Iemand is dubbel geboekt | geen stap; een signaal op Bemensing | planner | buiten het verloop, bewust |
| De opdracht wordt verlengd of de begroting groeit na akkoord | geen stap | eigenaar | **gat**; ontwerp hieronder, niet gebouwd |
| Interne opdracht | een eigen kort verloop: Begroting, Starten, Uitvoeren; starten is een knop in de kop, zonder offerte of akkoord | eigenaar | nagelopen in de browser, werkt |

### Iemand werven

**Hoofdgeval.** Een planner opent een vacature voor een open rol, vult de aanvraag in, vraagt aan, krijgt advies van HR en concern control en het akkoord, stelt open en legt vast wie is aangenomen. Begint op: Vacatures, of Bemensing van de opdracht.

| Variant | Wat het verloop toont | Wie is aan zet | Status |
|---|---|---|---|
| Hoofdgeval | Aanvraag, Advies en akkoord, Openstellen, Vervullen | aanvrager; bij advies de adviseur | nagelopen, werkt |
| De aanvraag mist gegevens | de zin zegt dat, eronder wat ontbreekt; de knop opent het formulier | aanvrager | nagelopen, werkt |
| De kandidaat is al bekend | de stap Openstellen ontbreekt | aanvrager | nagelopen, werkt |
| Een adviseur werkt buiten grip | de zin zegt dat de aanvrager het advies zelf opvraagt en wie het kan vastleggen | aanvrager, daarna een beheerder | nagelopen, werkt |
| Er is niemand genoemd voor een advies | de zin vraagt het op te vragen en vast te leggen | aanvrager | nagelopen, werkt |
| Openstellen zonder dat het akkoord in grip staat | Openstellen telt als gedaan, Advies en akkoord blijft de huidige stap | wie akkoord vastlegt | getest |
| De vacature wordt ingetrokken | geen stappen meer, de stand Ingetrokken, geen knop | niemand | nagelopen, werkt |
| Vervuld | alle stappen gedaan, de stand Vervuld | niemand | getest |

### Een tekst schrijven

**Hoofdgeval.** De aanvrager schrijft de vacaturetekst, biedt haar aan voor een oordeel, verwerkt de opmerkingen en stelt haar vast. Begint op: de tab Tekst van de vacature.

| Variant | Wat het verloop toont | Status |
|---|---|---|
| Hoofdgeval | Schrijven, Beoordelen, Vaststellen | op de tab Tekst staat per tekst wie aan zet is; een lege tekstpagina biedt de standaardtekst, een tekst op maat of zelf schrijven. Nagelopen; het beoordelen zelf niet |
| De tekst komt twee keer terug | Schrijven is weer de huidige stap, zo vaak als nodig | idem |
| Vaststellen zonder oordeel | Beoordelen telt als gedaan zodra de tekst is vastgesteld | idem |

## Welke processen een verloop hebben

Een verloop is er waar meer stappen over de tijd lopen, meer mensen handelen en iemand moet weten waar het staat. De rest is de stand van een gegeven en krijgt hooguit een label.

| Proces | Verloop | Waarom |
|---|---|---|
| Potentiële opdracht tot akkoord | ja | dagen tot weken, eigenaar, goedkeurder en opdrachtgever |
| Opdracht in uitvoering | ja | maanden, planner, manager, eigenaar |
| Ontvangen offerte bij de opdrachtgever | ja | aanvrager wacht, tekenbevoegde besluit |
| Offerte zelf | nee; haar kaart toont een label en hoe ze is aangeboden | zij is de stappen Offerte tot Akkoord van de opdracht; een tweede balk zegt het twee keer |
| Vacature | ja | weken, aanvrager, adviseurs, directie |
| Vacaturetekst en motivatie | ja | rondes tussen schrijver en beoordelaars |
| Factuurperiode | ja | afsluiten, aanleveren, factuur, over maanden |
| Maand afsluiten | nee | een handeling van een persoon; een taak en een formulier |
| Tarievenkaart | nee | concept of vastgesteld; een label |
| Persoon | nee | gebeurtenissen (promotie, inhuur), geen weg met een einde |
| Factuur van een kostenpost | nee | verwacht of ontvangen; een label |
| Voorstellen uit Wies | nee | een lijst om te bevestigen |
| Aanvraagformulier | nee | twee taken binnen de stap Advies en akkoord van de vacature |
| Interne goedkeuring | nee | een stap van de opdracht, een taak voor de goedkeurder |
| Een instantie koppelen | nee | een keer, door een beheerder |

## Het patroon

Een pagina van een zaak met een verloop zegt van boven naar beneden, overal op dezelfde plek:

1. **Wat er nu gebeurt**, in een zin aan de lezer, direct onder de titel. Is de lezer aan zet, dan staat rechts van de titel de ene knop die de stap zet, met de naam van de stap. Is een ander aan zet, dan zegt de zin wie en is er geen knop.
2. **Wat nog ontbreekt** voor die stap, alleen zolang er iets ontbreekt, en de termijn. Een verlopen termijn staat rood.
3. **Het verloop**: drie tot vijf stappen, klein en rustig. Een stap die niet van toepassing is ontbreekt. Een stap die gedaan is telt als gedaan waar hij ook staat.
4. **Het werk** van de huidige stap op de tabs eronder.
5. **Wat er gebeurd is**: de tab Geschiedenis.

Een lijst zegt per zaak hetzelfde in een kolom Stand: de stap, en eronder "Jij: ..." of "Wacht op ...".

Regels:

- **Een accent per pagina.** Draagt de kop de volgende stap, dan stapt de hoofdknop van de tab terug naar een gewone knop. Staat de lezer al op de plek waar de stap wordt gezet, dan draagt de pagina de knop en de kop niet.
- **De knop doet de stap** waar dat een enkele beslissing is (in uitvoering zetten, een formulier openen); anders brengt hij naar de plek waar de stap wordt gezet.
- **Dezelfde woorden** in de zin, de knop, de taak, de lijst en de melding. Ze staan op een plek: `backend/grip/data/tasks/guidance.json`.
- **Geen doodlopend punt.** In elke stand is er een huidige stap die iemand iets vertelt, of het verloop is voorbij. Een test loopt elke combinatie van feiten na.
- **Harde volgorde alleen waar het domein die eist.** Dat zijn er drie: aanbieden kan pas na interne goedkeuring waar die vereist is (iemand anders moet de offerte hebben gezien voor zij de deur uit gaat); aanleveren kan pas als alle maanden van de periode zijn afgesloten (het bedrag staat anders niet vast); een tekst gaat pas de deur uit als zij is vastgesteld. Al het andere mag in elke volgorde.
- **Teruggaan heeft een naam**: een nieuwe offerte maken (de oude vervalt), terugsturen met een reden, opmerkingen verwerken, een maand heropenen, een vacature intrekken. De stap waar het verloop op terugvalt wordt weer de huidige.

## Stappen en taken

Elke stap waar iemand moet handelen is een taak voor precies die persoon. De taak ontstaat en sluit door hetzelfde feit dat de stap afrondt; niemand vinkt haar af. Een test faalt als een taak bij geen stap hoort, of als een stap waar iemand moet handelen niemand iets vertelt.

### Offerte van de opdrachtnemer (de zaak zelf)

| Stap | Wie handelt | Taak | Knop | Waar | Sluit als |
|---|---|---|---|---|---|
| Aanvraag | niemand | | | | volgt uit de zaak zelf |
| Offerte ontvangen | niemand | | | | Je wacht op de offerte van de opdrachtnemer. |
| Besluit | tekenbevoegde | Beoordeel de ontvangen offerte | Beoordeel de offerte | Ontvangen offerte | er is akkoord gegeven of afgewezen |

### Naar een akkoord (de zaak zelf)

| Stap | Wie handelt | Taak | Knop | Waar | Sluit als |
|---|---|---|---|---|---|
| Begroting | eigenaar | Maak de begroting | Maak de begroting | Begroting | de begroting heeft een regel |
| Offerte | eigenaar | Maak de offerte | Maak offerte | Offerte | er is een offerte die geldt en bij de begroting past |
|  | wie de offerte maakte | Maak een nieuwe offerte | Pas de begroting aan | Begroting | er is een nieuwe offerte uitgegeven |
|  | eigenaar | Maak een nieuwe offerte na de afwijzing | Maak een nieuwe offerte | Offerte | er is een nieuwe offerte uitgegeven |
| Interne goedkeuring | eigenaar | Vraag interne goedkeuring | Vraag goedkeuring | Offerte | interne goedkeuring is gevraagd |
|  | offertegoedkeurder | Beoordeel offerte {kenmerk}, binnen 3 werkdagen | Beoordeel de offerte | Offerte goedkeuren | de offerte is goedgekeurd of teruggestuurd |
| Aanbieden | eigenaar | Bied de offerte aan | Bied de offerte aan | Offerte | de offerte is aangeboden |
| Akkoord | eigenaar | Leg het akkoord van de opdrachtgever vast | Bekijk de offerte | Offerte | de opdrachtgever heeft akkoord gegeven |

### Uitvoering (de zaak zelf)

| Stap | Wie handelt | Taak | Knop | Waar | Sluit als |
|---|---|---|---|---|---|
| Akkoord | niemand | | | | volgt uit de zaak zelf |
| Starten | eigenaar | Zet de opdracht in uitvoering | Zet in uitvoering | Overzicht | de opdracht is in uitvoering |
| Uitvoeren | planner | Vul de rol {rol} in | Vul de rol in | Bemensing | de rol is ingevuld |
|  | eigenaar of manager | Sluit {maand} af, binnen 5 werkdagen | Sluit {maand} af | Afsluiten en factureren | de maand is afgesloten |
|  | eigenaar of manager | Lever {periode} aan, binnen 5 werkdagen | Lever aan | Afsluiten en factureren | de periode is aangeleverd |
|  | eigenaar of manager | Leg de factuur over {periode} vast, binnen 10 werkdagen | Leg factuur vast | Afsluiten en factureren | de factuur over de periode is vastgelegd |
|  | eigenaar of manager | Lever de naverrekening van {maand} aan, binnen 5 werkdagen | Lever de naverrekening aan | Afsluiten en factureren | de naverrekening is aangeleverd |
| Verantwoorden | eigenaar | Lever het eindrapport op | Maak het eindrapport | Rapportage van de opdracht | het eindrapport is uitgegeven |

### Interne opdracht (de zaak zelf)

| Stap | Wie handelt | Taak | Knop | Waar | Sluit als |
|---|---|---|---|---|---|
| Begroting | eigenaar | Maak de begroting | Maak de begroting | Begroting | de begroting heeft een regel |
| Starten | eigenaar | Start de opdracht | Start de opdracht (in de kop, in een keer) | Overzicht | de opdracht is in uitvoering |
| Uitvoeren | planner, eigenaar of manager | dezelfde taken als bij Uitvoering | | | de opdracht is afgerond |

### Factuurperiode (per factuurperiode)

| Stap | Wie handelt | Taak | Knop | Waar | Sluit als |
|---|---|---|---|---|---|
| Maanden afsluiten | eigenaar of manager | Sluit {maand} af, binnen 5 werkdagen | Sluit {maand} af | Afsluiten en factureren | de maand is afgesloten |
| Aanleveren | eigenaar of manager | Lever {periode} aan, binnen 5 werkdagen | Lever aan | Afsluiten en factureren | de periode is aangeleverd |
| Factuur | eigenaar of manager | Leg de factuur over {periode} vast, binnen 10 werkdagen | Leg factuur vast | Afsluiten en factureren | de factuur over de periode is vastgelegd |

### Werving (de zaak zelf)

| Stap | Wie handelt | Taak | Knop | Waar | Sluit als |
|---|---|---|---|---|---|
| Aanvraag | aanvrager | Vraag de vacature aan | Vraag aan | Aanvraag | de aanvraag is ingediend |
| Advies en akkoord | adviseur HR | Geef het advies van HR, binnen 5 werkdagen | Leg het advies vast | Advies en akkoord | het advies van HR is vastgelegd |
|  | adviseur concern control | Geef het advies van concern control, binnen 5 werkdagen | Leg het advies vast | Advies en akkoord | het advies van concern control is vastgelegd |
|  | wie akkoord geeft | Geef akkoord op de vacature | Leg het akkoord vast | Advies en akkoord | het akkoord is vastgelegd |
|  | aanvrager | Maak het aanvraagformulier | Maak aanvraagformulier | Aanvraag | het aanvraagformulier is gemaakt en klopt met de vacature |
|  | aanvrager | Leg het getekende formulier vast | Leg getekend formulier vast | Aanvraag | het getekende formulier is vastgelegd |
| Openstellen | aanvrager | Stel de vacature open | Stel open | Procedure | de vacature is opengesteld |
| Vervullen | aanvrager | Leg vast wie is aangenomen | Vervul | Vervulling | de aanname is vastgelegd |
|  | aanvrager | Leg de link naar de gepubliceerde vacature vast | Leg de link vast | Tekst | de link naar de gepubliceerde vacature is vastgelegd |
|  | aanvrager | Stel de nieuwe collega voor aan Wies | Bekijk de vervulling | Vervulling | de collega is bekend in Wies |
|  | aanvrager | Vraag een account en e-mailadres aan | Bekijk de vervulling | Vervulling | de collega heeft een e-mailadres |

### Tekst (per tekst)

| Stap | Wie handelt | Taak | Knop | Waar | Sluit als |
|---|---|---|---|---|---|
| Schrijven | schrijver | Schrijf de {tekst} | Schrijf de {tekst} | Tekst | de tekst is vastgesteld |
|  | schrijver | Verwerk de opmerkingen op de {tekst} | Verwerk de opmerkingen | Tekst | er is een nieuwe versie of de tekst is vastgesteld |
| Beoordelen | beoordelaar | Beoordeel de {tekst}, binnen 3 werkdagen | Beoordeel de {tekst} | Tekst | het oordeel is gegeven |
| Vaststellen | schrijver | Schrijf de {tekst} | Schrijf de {tekst} | Tekst | de tekst is vastgesteld |

Gaten die bij het opstellen van deze tabel zijn gevonden en gedicht:

- Niemand kreeg te horen dat interne goedkeuring gevraagd moest worden. Er is nu de taak "Vraag interne goedkeuring" voor de eigenaar.
- "Bied de offerte aan" verscheen ook als de offerte nog niet goedgekeurd was. De taak ontstaat nu pas als niets meer in de weg staat.
- Een verlopen offerte, of een offerte die niet meer bij de begroting past, leidde tot geen taak. "Maak de offerte" gaat nu weer open, met de reden in de zin.
- De knop bij advies en akkoord heette "Leg vast". Hij heet nu naar wat hij vastlegt.

## Wat nog niet wordt ondersteund

- **Naverrekening als stap.** De taak "Lever de naverrekening over {periode} aan" staat in het plan met haar woorden ("Na de aanlevering van {periode} is er iets gewijzigd; het verschil is {bedrag}."), maar ontstaat nog niet: grip legt niet vast dat een correctie is ontstaan, en dat per evaluatie uitrekenen is te duur. Het kleinste ontwerp: een rij per ontstane correctie (opdracht, periode, verschil in centen, ontstaan op), geschreven op het moment dat een aangeleverde maand anders geprijsd wordt. Het feit, het bedrag in de zin en een vierde stap "Naverrekenen" in het verloop van de periode volgen daaruit.
- **Het ontvangen verloop bij de opdrachtgever** staat in de kop van de aanvraag, maar is alleen bekeken met een nagemaakte aanvraag in een kopie, niet met twee gekoppelde instanties.

## Ontwerp: verlengen of groeien na akkoord

Niet gebouwd. Het voorstel is een aanvullende offerte op dezelfde opdracht.

**Wat de gebruiker ziet.** De opdracht blijft in uitvoering: maanden sluiten en factureren gaan door op wat getekend is. Wijzigt de begroting na het akkoord (meer inzet, een latere einddatum), dan zegt de kop: "De begroting wijkt € X af van wat getekend is. Maak een aanvullende offerte." Onder het verloop van de uitvoering verschijnt een tweede, korte regel "Aanvulling: Offerte, daarna aanbieden", als onderdeel van de zaak, net als een factuurperiode. De eigenaar loopt Offerte, (Interne goedkeuring), Aanbieden en Akkoord nog een keer. Na het akkoord is de aanvulling getekend en verdwijnt de regel.

**Waarom zo en niet anders.**

- Een nieuwe opdracht voor de verlenging knipt de uitputting, de bemensing en de geschiedenis in tweeën, terwijl de opdrachtgever het als een opdracht ziet.
- De opdracht terugzetten naar potentieel zou afsluiten en factureren blokkeren voor werk dat al getekend is.
- Een offerte is een bevroren momentopname. De aanvullende offerte bevriest dus alleen het verschil met wat eerder getekend is, of de nieuwe stand met een verwijzing naar de vorige; de eerste blijft ongewijzigd geldig.

**Wat het vraagt.**

- Rekenen: "getekend" wordt de som van alle getekende offertes van de opdracht; het verschil tussen begroting en getekend is een afgeleide waarde in `grip.calc`.
- Offertes: uitgeven mag ook bij een opdracht in uitvoering, als aanvulling; afwijzen van een aanvulling laat de status van de opdracht met rust.
- Plan: een onderdeel `supplement` met het feit "begroting wijkt af van getekend" en een verloop van vier stappen; de bestaande taken voor offerte, goedkeuring en aanbieden gelden ook voor dit onderdeel.
- Factureren: tot het akkoord op de aanvulling is het meerwerk niet aan te leveren. Dat is een regel die nu niet bestaat en die de opdrachtgever raakt.

Het raakt rekenregels, de offerte als bevroren stuk en het contract met de opdrachtgever. Daarom eerst een besluit (ADR), dan bouwen.

## Voor wie het plan aanpast

Het verloop staat per soort zaak in `backend/grip/data/tasks/plan.json` onder `courses`: de stappen, hun naam, de feiten die een stap afronden (`done_when`), de feiten waaronder een stap bestaat (`when`), de taken die bij de stap horen en wat er bij een stap gezegd wordt (`notes`, `idle`). Onder `ends` staat hoe een zaak kan eindigen. Een feit met een punt erin gaat over een onderdeel van de zaak (`quote_round.quote_offered`). Een plan kan geen feit noemen dat grip niet berekent; dat faalt bij het laden. Een variant voor een andere organisatie is een wijziging van dit bestand.
