# ODI voert de administratie: inkoop, factuur en betaalbaarstelling over instanties heen

Ontwerp voor project 3 van stap 3 (de voorbeeldorganisaties). Datum: 28 november 2026. Status: voor de eigenaar van grip, na een controle door een bouwer.

## 1. Waarom

Grip beproeft hoe informatie tussen onderdelen van de Rijksoverheid loopt: elke organisatie een eigen instantie, en tussen de instanties FSC. Tot nu toe is de eigenaar van een gegeven de partij die het laat ontstaan (ADR 0053). Bij een kostenpost die DigiGilde voor MOZa uitvoert, is dat DigiGilde (ADR 0052). Een moederinstantie haalt alleen totalen op en bewaart niets (ADR 0016).

De eigenaar van grip ziet het anders, en zo werkt het in de praktijk:

- ODI is een agentschap en voert de administratie. Facturen en kosten horen daar te liggen. (Formeel is de Staat de rechtspersoon; ODI is de partij die de administratie voert.)
- DigiGilde is een merk van ODI. DigiGilde en MOZa krijgen via FSC alleen te zien wat ODI voor hen labelt of openzet.
- Een inkoop gaat niet zonder goedkeuring van iemand met het juiste mandaat: de manager van een merk tot zijn grens, daarboven de directeur.
- Een factuur wordt niet zomaar betaald. De aanvrager verklaart dat geleverd is. Boven een grens keurt ook de manager of directeur de factuur goed, zodat niemand alleen iets aan een bekende kan laten uitbetalen. De controller ziet de hele keten (wie keurde wat goed, wanneer, op welk mandaat, en of er budget is) en stelt pas dan betaalbaar.
- Mandaten zijn beslisregels. Die lenen zich voor RegelRecht.

In de woorden van de eigenaar: "dat een factuur niet zomaar wordt uitbetaald, maar alleen als het ook qua mandaat goedkeuring en budget klopt."

## 2. Doelen, niet-doelen, anti-doelen

**Doelen**

1. ODI draait als voorbeeldinstantie in de groep `grip-voorbeeld`, als moeder van DigiGilde.
2. Een inkoopzaak ligt bij ODI: aanvraag, goedkeuringen, opdracht, factuur, leveringsverklaring, controle en betaalbaarstelling. Elke stap is een feit in de kroniek van ODI, met wie het vaststelde, wanneer en op welke grond.
3. Invoeren kan vanuit elke betrokken grip: MOZa, DigiGilde en ODI zelf. Goedkeuren doet elke partij in de eigen grip; het besluit gaat met bewijs naar ODI.
4. Goedkeuren kan vooraf (de uitgave mag gedaan worden) en achteraf (de factuur klopt en is geleverd). Grip moet allebei kunnen.
5. Mandaten staan als regels in deze repo en worden uitgevoerd door de engine van RegelRecht. Een regel toetst of een goedkeuring geldig is, en kan in afgesproken gevallen zelf goedkeuren.
6. De controller ziet bij een factuur de keten en het oordeel van de regels, en besluit over betaalbaarstelling.
7. ODI bepaalt met labels wat DigiGilde en MOZa van een inkoopzaak zien.
8. In de demo is het na te spelen, met verzonnen mensen en bedragen.

**Niet-doelen**

- Betalen. Grip betaalt niet. Wel weet grip dat een factuur betaald is: idealiter via een koppeling met het boekhoudsysteem, tot die er is met de hand (de eigenaar, 28 november). Dat wijzigt ADR 0012 ("volgt geen betaling") en ADR 0023 ("betaald: grip weet het niet") voor inkomende facturen.
- Een echt mandaatbesluit of een juridisch oordeel over automatisch besluiten in mandaat. Alles is een verzonnen voorbeeld.
- FTV als extern beslispunt. `decide()` blijft de enige beslisser; de labels worden zo gebouwd dat een AuthZEN-beslispunt het later kan overnemen (ADR 0008).
- Verkoop: offertes, opdrachten en factuurgegevens van DigiGilde aan zijn opdrachtgevers blijven zoals ze zijn.

**Anti-doelen** (wat het mislukt maakt, ook als het technisch werkt)

- Een factuur die betaalbaar wordt zonder geldige goedkeuring, zonder leveringsverklaring of buiten het budget, zonder dat de controller het ziet.
- Iemand die zijn eigen aanvraag of factuur goedkeurt, of een tweede goedkeuring die van dezelfde persoon komt.
- Een kopie van de factuur bij DigiGilde of MOZa die gaat afwijken van die bij ODI.
- Een regel die besluit zonder dat achteraf te zien is welke regel, welke versie, met welke invoer.
- Iets uit de klassen D, E en F dat over de grens gaat.

## 3. De partijen in het voorbeeld

Uit het personaboek (`docs/personas/`). De mandaten zijn daar al tekst; dit ontwerp maakt er regels van.

| Partij | Persona | Rol in de keten | Mandaat volgens het personaboek |
|---|---|---|---|
| ODI | ODI-AD, algemeen directeur | keurt boven de grens van een merk goed | tot € 5.000.000 per verplichting |
| ODI | ODI-DIG, directeur digitalisering | directeur boven DigiGilde | tot € 5.000.000 |
| ODI | ODI-BV, directeur bedrijfsvoering | eigenaar van de financiële administratie | tot € 5.000.000 |
| ODI | ODI-BC, business controller | controleert de keten en stelt betaalbaar | geen mandaat om te verplichten |
| DigiGilde | GLD-MGR, hoofd DigiGilde (manager van het merk) | keurt aanvragen en facturen goed tot haar grens | tot € 500.000 |
| DigiGilde | GLD-VAK, vakgroepleider | keurt goed tot haar grens | tot € 30.000 |
| DigiGilde | GLD-PLAN, planner (teamleider) | keurt goed tot zijn grens | tot € 15.000 |
| DigiGilde | GLD-EIG, opdrachteigenaar | vraagt aan, verklaart levering | geen mandaat |
| DigiGilde | GLD-BEH, beheerder (ondersteuning) | voert facturen in | geen mandaat |
| MOZa | PRG-DIR, programmadirecteur | keurt goed voor het programma | € 50.000, als directeur € 2 miljoen |
| MOZa | PRG-CTRL, programmacontroller | vraagt aan, voert in, keurt goed tot haar grens | ondermandaat tot € 50.000 |

**Wie de taak krijgt (keuze van de ontwerper).** Een aanvraag noemt het onderdeel waar de uitgave onder valt (bij DigiGilde: het merk, en daarbinnen de vakgroep of het team). De taak om goed te keuren gaat naar de mensen in de lijn van dat onderdeel met de laagste grens die het bedrag dekt; wie hoger in de lijn staat, mag het ook. Een tweede goedkeuring gaat naar de eerstvolgende in de lijn met een grens die het bedrag dekt, en nooit naar de aanvrager of wie de levering verklaarde.

**Waar functie en mandaat vandaan komen (keuze van de ontwerper).** Grip kent nu alleen rechten (ADR 0009), geen functies. Elke instantie legt bij haar eigen mensen vast welke functie ze hebben, vanaf en tot wanneer. Elke organisatie heeft een eigen mandaatregeling (ODI, en MOZa naar het voorbeeld van het Mandaatbesluit BZK). Een goedkeurder keurt goed in de eigen grip; die grip toetst het mandaat met de eigen regeling en stuurt de uitkomst ondertekend mee met het besluit. ODI vertrouwt dat zoals het nu een ondertekend akkoord vertrouwt (ADR 0029). Dat wijzigt ADR 0029, dat zegt dat het mandaat buiten grip vastligt: voor deze voorbeelden ligt het mandaat als regel in grip.

**Keuze van de ontwerper:** het "MOZa-team" is PRG-CTRL en PRG-DIR; "DigiGilde-management" is GLD-MGR, GLD-VAK en GLD-PLAN, elk tot de eigen grens; "DigiGilde-ondersteuning" is GLD-BEH. ODI-BC wordt de controller die betaalbaar stelt; haar persona krijgt die handeling erbij. De personas van ODI krijgen schermen en rechten, die nu overal "nee" zijn.

## 4. De keten

Eén inkoopzaak bij ODI doorloopt deze stappen. Elke stap is een feit in de kroniek van de zaak, bij ODI.

1. **Aanvraag.** Iemand vraagt een uitgave aan: omschrijving, verwacht bedrag, periode, ten laste van welke opdrachtgever en begrotingsregel, en de leverancier. Dat kan bij ODI zelf, of vanuit MOZa of DigiGilde: dan is het een verzoek aan ODI, zoals nu het verzoek om een kostenpost (ADR 0052), en houdt de aanvrager een verwijzing (ADR 0053).
2. **Goedkeuring vooraf.** Wie moet goedkeuren, volgt uit de regels: de opdrachtgever (MOZa) als het ten laste van MOZa gaat, en binnen ODI iemand met mandaat voor het bedrag. Elke goedkeurder doet dat in de eigen grip. Het besluit gaat ondertekend naar ODI en ligt daar vast als besluit van een ander, met bewijs (zoals het akkoord op een offerte, ADR 0029). Een mandaatregel kan een goedkeuring ook zelf geven (zie 6). Pas na alle verplichte goedkeuringen mag de uitgave gedaan worden: de verplichting is aangegaan.
3. **Opdracht aan de leverancier.** De verplichting krijgt de leverancier met zijn KvK-gegevens (KvK-nummer, naam, vestiging). Hoe die gegevens binnenkomen, is een open vraag (hoofdstuk 11).

**Hoe een aanvraag uit MOZa bij ODI komt (keuze van de ontwerper).** MOZa kiest zoals nu bij "Uitgevoerd door" DigiGilde. De grip van DigiGilde geeft het verzoek door aan haar moeder ODI, die eigenaar wordt; het antwoord aan MOZa noemt het adres van de zaak bij ODI, zodat de verwijzing van MOZa naar ODI wijst. MOZa hoeft ODI niet te kennen als partij.
4. **Factuur.** De factuur van de leverancier komt binnen en wordt ingevoerd, bij ODI of vanuit DigiGilde of MOZa, met de pdf. Grip legt hem naast de verplichting: dezelfde leverancier (KvK-nummer), het bedrag binnen wat is goedgekeurd, de periode. Wat niet klopt, wordt een bevinding voor de controller; het houdt de keten niet tegen.
5. **Levering verklaren.** De aanvrager keurt de factuur goed en verklaart daarmee dat geleverd is wat besteld was. Een aanvraag vanuit een andere grip verklaart ook in die grip.
6. **Tweede goedkeuring.** Vanaf een grens die een regel bepaalt, keurt ook een manager of directeur met mandaat de factuur goed. Dat is nooit de aanvrager of de leveringsverklaarder (vier ogen, ADR 0048).
7. **Controle.** Een regel rekent de keten na en geeft een oordeel met uitleg: zijn alle verplichte goedkeuringen er, had elke goedkeurder op de dag van zijn besluit het mandaat voor dit bedrag (volgens de versie van de regel van die dag), is de levering verklaard, past de factuur bij de verplichting, en is er budget (het beschikbare bedrag op de begrotingsregel, zoals grip dat al berekent, R6 tot en met R10).

   **Welk budget (keuze van de ontwerper).** De begrotingsregel van de partij ten laste van wie het gaat: bij een uitgave voor MOZa die van MOZa, live opgehaald bij MOZa; bij een uitgave van ODI zelf die van ODI. Is die grip niet bereikbaar, dan is het oordeel "onvolledig" (ADR 0053), niet "klopt niet", en de controller ziet dat. MOZa en DigiGilde rekenen hun uitputting met de factuurregels die ze bij ODI lezen, zoals MOZa dat nu bij DigiGilde doet.
8. **Betaalbaarstelling.** De controller van ODI ziet de keten en het oordeel, en stelt betaalbaar of stelt niet betaalbaar met een reden. Ook bij een oordeel "klopt niet" mag de controller beslissen, met reden; de kroniek toont dan beide. Een betaalbaargestelde factuur gaat naar het financiële systeem, zoals de factuurgegevens nu.

De drie stromen van de eigenaar vallen hierin:

| Stroom | Voert in | Keurt goed |
|---|---|---|
| MOZa voert in | PRG-CTRL in MOZa voorbeeld | DigiGilde-management, ODI binnen mandaat |
| ODI voert in | ODI zelf | MOZa (verplicht), DigiGilde (optioneel) |
| DigiGilde-ondersteuning voert in | GLD-BEH in DigiGilde voorbeeld | MOZa; het verloop staat bij ODI |

**De factuur staat bij de kostenpost (de eigenaar, 28 november).** Een inkomende factuur krijgt geen losse plek en hoort niet bij een factuurperiode (dat is de uitgaande factuur, ADR 0039). Ze hoort bij de uitgave of de verwachte kostenpost, en de pagina van de kostenpost toont haar eigen verloop: binnengekomen, vergeleken, geleverd, goedgekeurd, betaalbaar, betaald.

**Wanneer een mens moet kijken (de eigenaar, 28 november).**
- Klopt de factuur met de kosten die eerder verwacht en goedgekeurd zijn (leverancier, bedrag binnen de goedkeuring, periode), dan keurt een regel haar automatisch goed.
- Klopt er iets niet, dan controleert en keurt de opdrachtgever, bijvoorbeeld MOZa.
- Soms is het alleen bevestigen dat geleverd is; die bevestiging kan nog ontbreken, en dan wacht de factuur daarop.
- Bij grotere bedragen kijkt altijd iemand mee; bij heel grote bedragen de manager of de directeur. De grenzen staan in de regels.

## 5. Waar het staat en wie wat ziet

- **ODI is eigenaar** van de inkoopzaak en alles erin. Dat volgt het patroon van ADR 0053 (één eigenaar, elders een verwijzing); alleen de eigenaar verschuift van wie de uitgave doet naar wie de administratie voert. ADR 0052 en 0053 krijgen een "Later gewijzigd"-alinea, of een nieuwe ADR vervangt het deel van 0052 over wie eigenaar is.
- **MOZa en DigiGilde houden een verwijzing** naar de zaak en lezen bij ODI, binnen wat ODI ze laat zien.
- **Labels.** ODI zet per zaak, en waar nodig per onderdeel, voor welke partij het zichtbaar is. Een betrokken partij (aanvrager, goedkeurder, opdrachtgever ten laste van wie het gaat) ziet standaard wat ze nodig heeft voor haar eigen stap. Daarboven zet ODI meer open, ook voor heel ODI, zoals de eigenaar noemde met openstaande vacatures. `decide()` beslist op die labels; de vorm blijft die van een AuthZEN-verzoek, zodat een FTV-beslispunt het later kan overnemen. FTV kent sinds juni 2026 een vastgestelde NLgov-AuthZEN 1.0.0; een taal voor beleid schrijft het niet voor.
- **Standaard zichtbaar voor een betrokken partij (keuze van de ontwerper):** voor een goedkeurder het bedrag, de omschrijving, de leverancier met KvK-gegevens en de factuur zelf; voor iedereen in de zaak de namen en functies van wie aanvroeg en goedkeurde. Die namen zijn nodig voor de keten van de controller, en gaan binnen de Rijksoverheid mee, zoals de eigenaar eerder voor NLDD besliste. Al het andere alleen met een label van ODI.
- **Wat nooit over de grens gaat,** blijft zo: de klassen D, E en F, een salarisschaal, en namen alleen waar de regels het nu al toestaan.

## 6. Mandaten als regels

- **De regels staan in deze repo,** in het formaat van RegelRecht: een map `regels/` met per regeling een map en per versie een YAML-bestand, genoemd naar de datum vanaf wanneer het geldt, met Gherkin-scenario's ernaast zoals RegelRecht dat doet. Voorbeeld: `mandaatregeling_odi_voorbeeld`, met per functie een grens, naar de bedragen uit het personaboek.
- **Twee soorten regels:**
  1. Een **toets**: heeft deze persoon, met deze functie, op deze datum, mandaat voor dit bedrag? Gebruikt bij elke goedkeuring en in de controle (stap 7). Ook: welke goedkeuringen zijn verplicht voor deze zaak (de opdrachtgever, en binnen ODI wie, en vanaf welk bedrag een tweede goedkeuring van de factuur).
  2. Een **automatische goedkeuring**: in afgesproken gevallen geeft de regel de goedkeuring zelf, namens een partij. Het voorbeeld van de eigenaar: een uitgave onder € 5.000 waarvoor MOZa akkoord gaf, is goedgekeurd namens DigiGilde.
- **De engine van RegelRecht voert ze uit,** via het programma `evaluate`: JSON in (de regel, de gevraagde uitkomsten, de invoer, de datum) en JSON uit (de uitkomsten, het artikel, de versie van de engine, de hash van de regel). Het programma komt mee in het image van de backend, op een vaste versie. Een dienst in grip roept het aan en geeft de uitkomst aan de servicelaag.
- **De uitkomst wordt een feit.** Een goedkeuring door een regel ligt vast als besluit namens de partij, met als grondslag de regeling, het artikel, de versie en haar hash, de versie van de engine, de invoer en de uitkomst. Daarmee is het besluit later na te rekenen met de regel van toen. Een nieuwe versie van een regel is zelf ook een feit (een lexogram): wie stelde haar vast, vanaf wanneer. **Keuze van de ontwerper:** een versie in de repo geldt pas als iemand met de bevoegdheid in de eigen grip haar vaststelt (bij ODI de algemeen directeur), met de datum vanaf wanneer; dat feit staat in de kroniek van die instantie. De engine krijgt alle versies van een regeling mee en kiest die van de dag.
- **Wat RegelRecht nog niet kan:** mandaat is daar nog geen soort regeling (alleen het voorstel RFC-042), en `evaluate` geeft geen uitleg per stap. Tot dan is een mandaatregel een beleidsregel, en maakt grip de uitleg uit de tekst van het artikel, de invoer en de uitkomst.

## 7. Wat grip al heeft en wat erbij komt

**Al aanwezig:** de kroniek met feiten, wie vaststelde, de grondslag en het verschil tussen een eigen besluit en de vastlegging van een besluit elders (ADR 0056); het verzoek aan een eigenaar en de verwijzing (ADR 0052, 0053); een ondertekend besluit over instanties met bewijs (het akkoord op een offerte, ADR 0029); vier ogen (ADR 0048); taken uit feiten (ADR 0024); `decide()` in de vorm van AuthZEN (ADR 0008); de berekening van wat beschikbaar is op een begrotingsregel; de route voor doorgifte aan een moeder (ADR 0016), aan de kant die levert.

**Erbij:**

- ODI als voorbeeldinstantie: dataset, personas met rechten, peerletter (`o`; `e` is gereserveerd voor NLDD), PKI, sjablonen, bootstrap, de rol moeder in het peerregister (de bootstrap zet nu altijd `counterpart`), het portaal.
- Een inkoopzaak met een eigen kroniek bij ODI (ADR 0056 noemt een kroniek voor facturatie als later werk).
- Goedkeuren tussen instanties: een verzoek om goed te keuren van ODI naar een andere grip, een taak daar, en het ondertekende besluit terug. Nieuwe operaties in het contract `grip-opdrachtverkeer`, dat sinds ADR 0060 in deze repo staat.
- De leveringsverklaring, de tweede goedkeuring, de controle en de betaalbaarstelling.
- De koppeling met RegelRecht en de map `regels/`.
- Labels en de beslissingen erop in `decide()`, met lektests.
- Het scherm voor de controller: de keten van een factuur, met per stap wie, wanneer, op welk mandaat, het oordeel van de regels en het budget.

## 8. Wat er met de kostenpost Zaalhuur gebeurt

Vandaag vraagt MOZa DigiGilde om de kostenpost Zaalhuur, en DigiGilde is eigenaar. In dit ontwerp gaat zo'n verzoek naar ODI. **Keuze van de ontwerper:** de voorbeelddata verhuizen mee: MOZa vraagt de Zaalhuur aan bij ODI, DigiGilde keurt goed binnen mandaat (of de regel doet het, onder € 5.000 met akkoord van MOZa), en ODI is eigenaar. Het verzoek aan DigiGilde zoals het nu werkt, blijft bestaan voor organisaties zonder moeder.

## 9. Opbouw

Elke stap een eigen PR, die de eigenaar ziet voor de merge:

1. ODI als voorbeeldinstantie en moeder van DigiGilde, lokaal en op ZAD.
2. De inkoopzaak bij ODI: aanvraag vanuit elke grip, verwijzing, kroniek, labels.
3. Goedkeuren tussen instanties, vooraf, door mensen.
4. De factuur op de pagina van de kostenpost: vergelijking, leveringsverklaring, automatische en tweede goedkeuring, controle, betaalbaarstelling en betaald (eerst met de hand).
5. Mandaatregels via RegelRecht: eerst de toets, dan de automatische goedkeuring.
6. Betaald via een koppeling met het boekhoudsysteem.

Elke stap krijgt de ADR die haar keuzes vastlegt. De volgorde ten opzichte van NLDD voorbeeld (project 1) en volgen (project 2): **aanname van de ontwerper**, dit gaat voor.

## 10. Acceptatie in de demo

1. PRG-CTRL vraagt in MOZa voorbeeld de Zaalhuur aan (€ 3.200). Bij ODI staat de zaak, bij MOZa een verwijzing.
2. De regel keurt goed namens DigiGilde; de kroniek bij ODI zegt welk artikel, welke versie en waarom.
3. Een aanvraag van € 20.000 in een vakgroep van DigiGilde krijgt een taak voor GLD-VAK (tot € 30.000), niet voor GLD-PLAN (tot € 15.000).
4. De factuur komt binnen met een ander KvK-nummer dan bij de opdracht: de controller ziet het als bevinding.
5. PRG-CTRL verklaart de levering; boven de grens keurt ook de eerstvolgende in de lijn met mandaat de factuur goed; wie aanvroeg of de levering verklaarde, kan dat niet.
6. ODI-BC ziet de keten en het oordeel en stelt betaalbaar. Met een goedkeuring buiten mandaat zegt het oordeel "klopt niet" en waarom.
7. DigiGilde ziet van de zaak alleen wat ODI heeft gelabeld; een lektest op API-niveau bewijst het.
8. Na de nachtelijke terugzetting is het voorbeeld er weer.

## 11. Open voor de eigenaar

- **KvK-gegevens:** haalt grip ze op bij de KvK (het Handelsregister), of voert iemand ze bij de opdracht in?
- **Wie moet goedkeuren, en telt een aanvraag als goedkeuring?** Zie de vraag aan de eigenaar van 28 november.

## 12. Wat aan de bouwer is

- De namen van tabellen, feiten, operaties en schermen, binnen de vaste woorden van `docs/ontwerp.md`.
- Hoe de verwijzing en het lezen bij ODI precies lopen, binnen ADR 0053.
- De vorm van de labels, zolang `decide()` de enige beslisser blijft en de AuthZEN-vorm heel blijft.
- De bedragen in de voorbeeldregels, uit het personaboek.
- Hoe `evaluate` in het image komt (release van RegelRecht of zelf bouwen), op een vaste versie. Let op: de crate staat op 0.3.0, de laatste release-tag is `engine-v0.2.0`. `evaluate` kiest de versie van de dag alleen uit de regels die het meekrijgt (`extra_laws`), en noemt de ingangsdatum alleen met `--receipt`.

Melden, niet zelf oplossen: alles waar een ADR iets anders zegt dan dit ontwerp en dat hier niet genoemd is.
