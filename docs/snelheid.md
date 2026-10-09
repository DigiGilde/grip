# Snelheid op ware grootte

Grip is gebouwd en getest op voorbeeldgegevens: 8 opdrachten en 14 mensen. Een organisatie die jaren werk meeneemt heeft er honderden. Dit document zegt hoe je meet hoe grip zich dan gedraagt, wat het budget is en wat er nog boven zit.

## Het budget

| Wat | Grens |
|---|---|
| Een pagina is bruikbaar | binnen 1000 ms, op een warme server |
| Een verzoek dat een pagina bij het laden doet | hooguit 300 ms |
| Statements in één verzoek | hooguit 50 |

Niets groeit met de hele geschiedenis als je naar één ding kijkt.

## Gegevens op ware grootte

```
DATABASE_URL=postgresql+asyncpg://grip:grip@localhost:5434/grip_schaal just migrate
DATABASE_URL=postgresql+asyncpg://grip:grip@localhost:5434/grip_schaal just seed-scale
```

`just seed-scale` (`backend/grip/dev/seed_scale.py`) vult een lege database met een verzonnen organisatie: 150 mensen over vier jaar, 400 opdrachten (300 afgerond, 60 lopend, 40 potentieel) met 5 begrotingsregels gemiddeld, inzet, elke verstreken maand afgesloten, perioden aangeleverd en gefactureerd, een paar procent correcties, 150 vacatures, 300 kostenposten, tarievenkaarten per jaar met een wijziging halverwege, promoties, en 300.000 inzagen in de stroom. Alles gaat door de servicelaag, dus bedragen, gebeurtenissen en de hashketen zijn echt. Twee dingen niet: de pdf van een offerte en een factuurverzoek wordt één keer opgemaakt en daarna hergebruikt, en de inzagen worden rechtstreeks aan de stroom toegevoegd. Het duurt ongeveer negen minuten en geeft een database van ruim 600 MB. Dezelfde argumenten geven dezelfde gegevens. Het commando weigert buiten een lokale ontwikkelinstantie, net als `just seed`.

Wat de generator niet maakt: afgehandelde taken (alleen de open taken die de motor uit de stand afleidt, rond 800), beoordelingsrondes op vacatureteksten, en binnengekomen berichten van andere instanties.

## Meten

Start een server op die database met de meting aan, en de schermen als gebouwde versie:

```
cd backend && DEV_NO_AUTH=1 DEV_SPEED_TIMING=1 DATABASE_URL=... uv run uvicorn grip.core.app:create_app --factory --port 8031
cd frontend && npm run build && VITE_API_URL=http://localhost:8031 npx vite preview --port 5184
just check-speed --base http://speed.localhost:5184
```

`DEV_SPEED_TIMING=1` zet per antwoord een `Server-Timing`-kop met het aantal statements en de tijd in de database. Het werkt alleen samen met `DEV_NO_AUTH=1`; een uitgerolde instantie stuurt de kop nooit.

`just check-speed` opent elke pagina als elke soort lezer (beheerder, de eigenaar met de meeste opdrachten, de leidinggevende met de meeste mensen, planner, lezer, teamlid) in een browser zonder venster en meldt per pagina: wanneer ze bruikbaar is, hoeveel verzoeken ze doet, het traagste verzoek, het grootste aantal statements, de kilobytes, de tijd dat de pagina vastzat in lange taken en het geheugen. Een pagina wordt twee keer geopend; de tweede keer telt.

- `--calls` toont elk verzoek per pagina.
- `--only /inzet` meet een deel, `--readers beheerder,teamlid` een deel van de lezers.
- `--json uit.json` bewaart de meting; `--api uit.json` meet daarna alleen de verzoeken, zonder browser.
- `--first` meet iets anders: de eerste keer laden van de startpagina, Taken en Opdrachten in een browser die nog niets bewaard heeft, en nog eens met de bestanden bewaard, op het profiel van een trage kantoorlaptop.

De uitkomstcode is 1 als iets boven het budget zit. Het is geen poort in de bouwstraat. Dat kan het worden als de bouwstraat een database op ware grootte heeft (negen minuten genereren, of een bewaarde dump) en de drempels eerst gehaald worden; op een gedeelde bouwmachine horen de tijden dan ruimer te zijn dan het budget en de aantallen statements juist strak, want die hangen niet van de machine af.

## Stand van 9 oktober 2026

Gemeten op één ontwikkelmachine, 28 pagina's maal 6 lezers.

| | Voor | Na |
|---|---|---|
| Pagina's boven 1000 ms | 82 van 168 | 3 van 168 |
| Start (traagste lezer) | 18,1 s | 0,4 s |
| Rapportage, jaarverantwoording | 25,6 s | 0,4 s |
| Rapportage, de andere onderwerpen | 16 tot 21 s | 0,6 tot 0,9 s |
| Factureren | 12,5 s | 0,3 s |
| Team en Inzet | 4,2 tot 6,7 s | 0,6 tot 0,9 s |
| `/api/overview` | 16,8 s, 13.235 statements | 0,14 s, 15 |
| `/api/billing` | 12,4 s, 14.597 statements, 208 kB | 0,10 s, 14, 35 kB |
| `/api/reports/year-account` | 25,4 s, 12.400 statements | 0,05 s, 14 |
| JavaScript bij de eerste pagina (gzip) | 702 kB | 495 kB (na de ronde voor de schermen hieronder: 281 kB) |

Wat er veranderd is:

- **Onthouden tot er iets verandert** (ADR 0051). De cijfers van een opdracht, de stand van factureren per maand en per periode, de regels van de jaarverantwoording, de omzet en de declarabiliteit worden per wijziging één keer berekend.
- **Samen lezen.** Wat een lijst van opdrachten deelt (regels, inzet, tarieven, schalen, afsluitingen) wordt in één keer gelezen in plaats van per opdracht.
- **Toegang per verzoek.** De relaties van de lezer (rollen, inzet, mensen, kostenposten) worden één keer per verzoek gelezen, niet per rij.
- **De taakmotor** kijkt niet opnieuw naar alle zaken als de stroom en de dag niet veranderd zijn.
- **Het nieuws** leest de vacatures van zijn 800 gebeurtenissen in één keer.
- **Het inzetbord** leest en prijst alleen de inzet in zijn venster.
- **Factureren over alle opdrachten** krijgt van de server alleen de perioden die nog iets vragen (af te sluiten, aan te leveren, te factureren). Het scherm toonde de rest al niet; het is niet veranderd.
- **De teksteditor** (CodeMirror) zit niet meer in wat elke eerste pagina laadt.

Bewezen met de hele servertest met `READ_CACHE=verify` en met een vergelijking van 140 antwoorden van de oude en de nieuwe server op deze database, voor vijf soorten lezers: alle gelijk.

## De schermen, 9 oktober 2026

De eerste ronde liet twee dingen aan de kant van de schermen liggen: alle eigen code in één bestand, en lijsten die alles in één keer ophalen.

### Wat de eerste pagina laadt

De schil, de startpagina en Taken komen met de eerste pagina mee. Elke andere pagina is een eigen bestand en wordt opgehaald op weg erheen: zodra de muis of de focus op een link naar die pagina staat, en anders als de route wordt getekend. Een kop met tabs (een opdracht, een vacature) en de pagina erin worden naast elkaar opgehaald, niet na elkaar. Tijdens het ophalen blijft de vorige pagina staan; alleen bij de allereerste pagina staat er kort de gewone laadregel in de schil.

Van het designsysteem komt alleen mee wat de schil, de startpagina en Taken tekenen. De rest reist met de pagina die het gebruikt: de datumkiezer met een formulier, de teksteditor met een pagina waarop je schrijft. Welke onderdelen bij de schil horen staat als lijst in `frontend/vite.config.ts`.

| JavaScript, gzip | Voor | Na |
|---|---|---|
| Eigen code bij de eerste pagina | 189 kB | 29 kB |
| Designsysteem bij de eerste pagina | 216 kB | 148 kB |
| React en de rest | 95 kB | 94 kB |
| Samen, wat de eerste pagina tegenhoudt | 500 kB | 281 kB |
| Wat de startpagina in totaal ophaalt (met lettertype, stijl en gegevens) | 841 kB | 495 kB |

De startpagina haalde daarnaast, direct na het tekenen, de teksteditor met CodeMirror op (207 kB gzip), op elke pagina: de gedeelde tekstvelden registreerden de editor mee. Die registratie is gesplitst (`ui/text/register` en `ui/text/registerEditor`).

Gemeten met `just check-speed --first`: een browser zonder bewaarde bestanden, de processor vier keer trager, 10 Mbit/s en 40 ms vertraging, de middelste van drie.

| Eerste keer laden | Voor | Na |
|---|---|---|
| Startpagina, niets bewaard | 902 ms, 841 kB in 30 verzoeken | 725 ms, 495 kB in 42 verzoeken |
| Opdrachten, niets bewaard | 897 ms, 841 kB in 30 verzoeken | 709 ms, 488 kB in 53 verzoeken |
| Startpagina, bestanden bewaard | 210 ms | 133 ms |
| Opdrachten, bestanden bewaard | 151 ms | 142 ms |

Het verschil in tijd is kleiner dan het verschil in bytes: op één machine, met een server ernaast, is de lijn niet wat het langst duurt. Op een echte lijn weegt het zwaarder.

**Na een uitrol.** Een uitrol vervangt de bestanden. Een tabblad dat ervoor al openstond vraagt dan om een bestand dat niet meer bestaat en krijgt 404. De pagina laadt in dat geval één keer opnieuw: dat haalt de nieuwe index en de nieuwe namen. Blijft het bestand ook daarna weg (binnen een halve minuut), dan staat er "Deze pagina laden is niet gelukt" met "Laad opnieuw", in de vorm van elke andere laadfout. Nagelopen in een browser: 404 op het bestand van Team gaf één herlaadbeurt en daarna de pagina; een bestand dat weg blijft gaf één herlaadbeurt en de melding.

De service worker bewaart een bestand van de bouw alleen als het een bestand is: geen foutantwoord en geen pagina onder de naam van een bestand, want een bestand met een hash blijft voorgoed bewaard. Hij bewaart er hooguit 400; de oudste gaan eerst, zodat bestanden van eerdere uitrollen vanzelf verdwijnen. De index komt altijd van het netwerk. Antwoorden van de API bewaart hij nooit; dat is niet veranderd.

### Lijsten

| Lijst | Wat de server nu stuurt | Wat er op het scherm veranderde |
|---|---|---|
| Opdrachten | Eén weergave (potentieel, lopend, afgesloten), één pagina van vijftig, de tellingen van alle drie de weergaven en het totaal. Zoeken op de naam van de opdracht of de opdrachtgever gebeurt op de server | Een zoekveld in de balk, boven de rijen "51 tot en met 100 van 300 opdrachten", onder de rijen de paginering. De tellingen op de tabs volgen de zoekwoorden |
| Kosten | Eén pagina van vijftig, in de volgorde die het scherm al had (wat aandacht vraagt eerst, daarna op naam), met het totaal. Zoeken op de omschrijving | Hetzelfde zoekveld en dezelfde paginering. De volgorde bepaalt de server nu, niet het scherm |
| Team | Ongewijzigd: 150 mensen op één pagina is geen lange lijst | De pagina van één persoon vraagt het inzetbord nog maar om de rij van die persoon |

De server filtert, telt en snijdt pas na de toegangsbeslissing. Een telling of een pagina bevat dus alleen wat de lezer mag zien; tests op API-niveau bewijzen dat voor een teamlid, een buitenstaander en een eigenaar (`test_assignment_list_window.py`, `test_costs_api.py`, `test_board_api.py`). Zonder `page` geven beide adressen nog de hele lijst, voor andere afnemers.

De kostenlijst rekent op de server nog steeds alle kostenposten door om ze te kunnen sorteren; wat kleiner werd is wat over de lijn gaat en wat de browser tekent.

| Verzoek van de lijst | Voor | Na |
|---|---|---|
| `/api/assignments`, beheerder | 22 kB over de lijn, 12 statements | 3,5 kB, 9 statements |
| `/api/costs`, beheerder | 67 kB, 214 ms | 12 kB, 110 ms |
| `/api/allocations/board` op de pagina van een persoon, beheerder | 42 kB, 330 ms | 0,2 kB, 239 ms |

### Wat het scherm vroeg en niet toonde

- De pagina Opdrachten haalde bij het laden de organisaties op voor het formulier "Nieuwe opdracht" dat nog dicht was. Het formulier wordt nu pas opgebouwd als het opent.
- De pagina van een persoon haalde het hele inzetbord op (150 mensen, twaalf maanden, 41 kB) voor één rij. Zij vraagt nu die ene rij (`person_id`).
- De schil vroeg twee keer wie er is ingelogd: één keer voor de sessie en één keer voor de ontwikkelschakelaar. Dat is nu één verzoek, ook op een uitgerolde instantie.
- Opnieuw ophalen bij terugkeer naar het venster stond al uit. Een pagina waar je naar terugkeert toont wat er was en haalt op de achtergrond het nieuwe op; dat is zo gelaten.

Niet veranderd, wel gezien: in ontwikkeling haalt de schakelaar "Bekijk als" op elke pagina alle mensen op (12 kB). Op een uitgerolde instantie bestaat die schakelaar niet. De lijst Mensen haalt het hele inzetbord op om per persoon te zeggen wanneer er ruimte komt; dat is het traagste verzoek van die pagina.

### Per pagina, voor en na

Dezelfde database, de gebouwde schermen van voor en na, tweede keer laden, met `just check-speed`.

| Pagina | Beheerder voor | Beheerder na | Eigenaar voor | Eigenaar na |
|---|---|---|---|---|
| Start | 4973 ms | 428 ms | 311 ms | 475 ms |
| Taken | 176 ms | 160 ms | 195 ms | 210 ms |
| Opdrachten | 316 ms | 271 ms | 192 ms | 243 ms |
| Inzet | 446 ms | 602 ms | 603 ms | 580 ms |
| Kosten | 483 ms | 272 ms | 193 ms | 180 ms |
| Factureren | 319 ms | 322 ms | 165 ms | 165 ms |
| Team | 494 ms | 632 ms | 452 ms | 653 ms |
| Vacatures | 1127 ms | 1120 ms | 442 ms | 781 ms |
| Rapportage | 1021 ms | 1063 ms | 380 ms | 375 ms |
| Opdracht overzicht | 207 ms | 279 ms | 165 ms | 290 ms |
| Opdracht bemensing | 404 ms | 523 ms | 431 ms | 568 ms |
| Vacature | 209 ms | 329 ms | 162 ms | 187 ms |
| Persoon | 441 ms | 421 ms | 437 ms | 456 ms |

De 4973 ms van de startpagina voor de beheerder is de eerste lezer na het vullen van de database (punt 1 hieronder), geen verschil in de schermen.

## De server, tweede ronde, 9 oktober 2026

Gemeten op dezelfde database, met een server van voor en een van na de wijziging naast elkaar. Er liep ander meetwerk op dezelfde machine; de aantallen statements hangen daar niet van af, de tijden wel.

### De eerste lezer

| Verzoek | Na een herstart, voor | Na een herstart, na | Na een wijziging die alle opdrachten raakt, voor | Idem, na |
|---|---|---|---|---|
| `/api/billing` | 6,6 s, 7.414 statements | 1,3 s, 56 | 6,6 s, 7.414 | 0,9 s, 56 |
| `/api/overview` | 1,6 s, 28 | 1,8 s, 28 | 1,5 s, 28 | 0,4 s, 28 |
| `/api/reports/year-account` | 1,5 s, 756 | 0,9 s, 22 | 1,9 s, 756 | 0,45 s, 22 |
| `/api/reports/investment` | 0,8 s, 274 | 0,6 s, 46 | 1,0 s, 274 | 0,6 s, 46 |
| `/api/reports/steering` | 1,1 s, 64 | 1,1 s, 64 | 1,2 s, 64 | 1,2 s, 64 |
| `/api/tasks/mine` | 1,7 s, 2.187 | 0,8 s, 369 | 1,3 s, 1.678 | 0,6 s, 369 |

Wat er veranderd is:

- **Factureren leest samen.** De stand van factureren van alle opdrachten wordt in een vast aantal statements gelezen en daarna per opdracht opgebouwd, met dezelfde functies als voor één opdracht.
- **Een maand wordt één keer geprijsd.** `calc.closed_month_amount` prijst alle maanden van een inzet om er één te geven; per afgesloten maand gevraagd is dat het kwadraat van het aantal maanden. De nieuwe functie `calc.billing_lines_by_month` prijst de geplande maanden van een inzet één keer en geeft per maand precies wat `calc.billing_lines` geeft, ook de fout. Een test vraagt 300 gevallen op beide manieren.
- **Onthouden op inhoud** (aanvulling op ADR 0051). Na een wijziging die niet over één opdracht gaat wordt de invoer opnieuw gelezen en alleen gerekend voor de opdrachten waarvan de invoer anders is. Dat geldt voor de cijfers van een opdracht, het te leveren bedrag per maand en de jaarverantwoording.
- **De jaarverantwoording** leest de geaccepteerde offertes in twee statements in plaats van twee per opdracht; **de investeerruimte** leest de begroting van de interne opdrachten samen.

Een aparte verfijning van welke gebeurtenis welke opdracht raakt (een tarief alleen de opdrachten met maanden in dat jaar) is niet gebouwd: onthouden op inhoud doet hetzelfde zonder dat iemand die koppeling hoeft te onderhouden, en een fout erin kan geen verouderd bedrag geven.

Er wordt niet voorgerekend na een herstart. Het rekenwerk gebeurt in hetzelfde proces dat de verzoeken afhandelt, dus voorrekenen zou de eerste lezers net zo laten wachten. Wie leest terwijl een ander proces rekent, rekent zelf: er is nooit een oud bedrag.

Een uitrol draait één proces per replica. Elke replica heeft haar eigen geheugen en betaalt de eerste lezer zelf. De sleutels komen uit de database, dus replica's geven hetzelfde antwoord.

### Taken en vacatures

| Verzoek | Voor | Na |
|---|---|---|
| `/api/tasks/courses` voor 150 vacatures, elke keer | 1,3 s, 2.038 statements | 0,15 s, 40 |
| `/api/tasks/mine`, beheerder, warm | 82 statements | 24 |
| `/api/tasks/count`, beheerder, warm | 81 statements | 23 |
| De taaklus van de worker, eerste ronde | 2.187 statements | 1,0 s, 345 |
| De taaklus, volgende ronde zonder wijziging | | 0,15 s, 31 |

- De teksten, rondes, opmerkingen en feiten van vacatures worden samen gelezen, net als de stand van het aanvraagformulier; het sjabloon één keer in plaats van per vacature.
- De feiten van een opdracht voor de taakmotor blijven staan tot een gebeurtenis die opdracht raakt of tot de dag omslaat. Na een wijziging op één opdracht wordt alleen die opnieuw gelezen.
- Of de lezer deel heeft aan een vacature wordt voor alle taken samen bepaald.

### De stroom

Op 323.000 gebeurtenissen, waarvan 300.000 inzagen.

| Vraag | Voor | Na | Hoe |
|---|---|---|---|
| Activiteit, alleen wijzigingen, eerste bladzijde | 135 ms, 300.112 rijen overgeslagen | 0,1 ms | de index op de wijzigingen |
| Activiteit, volgende bladzijden | 0,1 ms | 0,1 ms | bladert al op volgnummer, niet op positie |
| "Wat is er gebeurd" | 96 ms, alle wijzigingen gesorteerd | 4 ms | dezelfde index, zonder sorteren |
| Is er iets veranderd (elk verzoek) | 0,05 ms, groeit met de inzagen sinds de laatste wijziging | 0,05 ms, vast | dezelfde index |
| Geschiedenis van één opdracht | 0,2 ms | | bestaande index |
| Gebeurtenissen over één persoon | 1,2 ms | | bestaande index |
| Alleen inzagen | 0,1 ms | | primaire sleutel |

Migratie `0042_stream_changes_index` voegt één index toe: de wijzigingen op volgorde (`stream_event (seq) WHERE type <> 'data.read'`). De drie vragen die hij bedient staan in de migratie. Verder is niets toegevoegd; de andere vragen lezen zoveel rijen als ze teruggeven.

Het stempel "de laatste gebeurtenis die niet over één opdracht gaat" liep terug door de stroom tot die gebeurtenis, bij elk verzoek. Een proces leest nu alleen wat er sinds zijn vorige blik bij kwam.

### Schrijvers tegelijk

Een transactie die een gebeurtenis schrijft houdt één slot op de stroom vast tot ze klaar is; zo krijgt elke gebeurtenis haar plaats in de keten in de volgorde van vastleggen.

| | Per seconde | Midden | 95 procent |
|---|---|---|---|
| 1 schrijver (een persoon opslaan) | 44 | 21 ms | 30 ms |
| 5 schrijvers | 60 | 80 ms | 100 ms |
| 20 schrijvers | 55 | 353 ms | 461 ms |
| 20 schrijvers over twee processen | 55 | 360 ms | 480 ms |
| 20 lezers van een pagina die een inzage logt | 121 | 155 ms | 274 ms |
| dezelfde 20 lezers naast 5 schrijvers | 107 | 177 ms | 299 ms |

Twee processen schrijven samen niet meer dan één: het slot bepaalt de grens, rond 55 wijzigingen per seconde. Een organisatie van 150 mensen komt op haar drukste moment aan een paar per seconde. Het slot is dus geen grens voor deze omvang.

Het risico zit niet in het aantal maar in de duur: een transactie die na haar eerste gebeurtenis iets langzaams doet (een pdf opmaken, een taalmodel aanroepen) houdt al die tijd elke andere wijziging tegen, en ook elke pagina die een inzage logt, want die schrijft aan het eind van het verzoek. Daarom:

- langzaam werk hoort voor de eerste gebeurtenis van een transactie of na de commit;
- een transactie die het slot langer dan een halve seconde vasthoudt staat nu in het log (`the event stream was locked for ...`), met de soorten gebeurtenissen erbij. Welke handelingen dat zijn is niet nagelopen.

Een inzage loggen kost een verzoek een paar milliseconden. Ze na het antwoord schrijven zou lezers losmaken van het slot, maar dan kan een inzage ontbreken als het proces tussen antwoord en schrijven stopt. Dat is een keuze over de volledigheid van het logboek en is niet gemaakt.

### De worker en het geheugen

- De taaklus: zie boven. De lus voor meldingen doet niets zolang niemand een apparaat heeft aangemeld; met apparaten is hij niet gemeten.
- De bewaartermijn van inzagen: 9 ms en 2 statements op 300.000 inzagen (er was niets oud genoeg om weg te halen).
- Het geheugen van een serverproces met alle rapporten van vier jaar voor vijf lezers: 249 MB, tegen ongeveer 120 MB voor een leeg proces. Het geheugen is nu begrensd op 8.000 waarden per geheugen (`READ_CACHE_MAX_ENTRIES`), in de orde van 150 MB.

### Bewezen

De hele servertest draait met `READ_CACHE=verify`, dat nu ook het onthouden op inhoud en het stempel narekent. Daarnaast zijn 95 antwoorden (19 verzoeken, vijf soorten lezers) van de server van voor en van na vergeleken: 86 gelijk. De 9 andere zijn geen verschil in bedragen of toegang: de lijst van opdrachten heeft sinds de ronde over de schermen een venster, en de activiteitenpagina met inzagen groeit met elke meting.

## Wat nog boven het budget zit

In volgorde van wat het de gebruiker kost.

1. **De eerste lezer na een herstart**: Factureren 1,3 s, de startpagina 1,8 s, de jaarverantwoording 0,9 s, eenmaal per proces. Wat overblijft is het rekenen zelf in `grip/calc` (exacte breuken per maand en per stuk van een maand). **Na een wijziging die alle opdrachten raakt**: Factureren 0,9 s, de rest onder een halve seconde. Bij Factureren is dat het opnieuw opbouwen van de perioden van 360 opdrachten uit wat gelezen is.
2. **Sturing na elke wijziging**: `/api/reports/steering` rekent de bezetting van 150 mensen opnieuw na elke gebeurtenis, 1,2 s. Het rust op de hele stroom in plaats van op wat het leest.
3. **De taakmotor na een wijziging die alle opdrachten raakt** (een persoon, een functie): 369 statements en 0,6 s voor de eerste lezer. De opdrachten met een offerte die loopt worden een voor een nagelopen (goedkeuring, begroting tegenover offerte).
4. `/api/reports/investment`: warm 0,1 s en 34 statements; na een wijziging 0,6 s.
5. `/api/reports/steering`: 0,5 s; de bezetting van 150 mensen wordt elke keer berekend en het antwoord is 790 kB ongecomprimeerd.
6. `/api/allocations/board`: 0,2 tot 0,45 s en tot 39 statements; elke inzet in het venster wordt bij elk verzoek geprijsd.
7. `/api/events` voor wie geen beheerder is: 14 tot 167 statements per bladzijde, toegang per gebeurtenis.
8. **De tweede keer laden werd niet sneller.** De tabel "Per pagina, voor en na" laat zien dat een pagina die al eens geladen is even snel is als voorheen, binnen de ruis van de meting (ongeveer 100 ms; er liep ander werk op dezelfde machine). De winst van het splitsen zit in de eerste keer laden en in wat er over de lijn gaat. De pagina's van één opdracht waren in deze meting 50 tot 100 ms trager: de proefserver laat de browser elk bewaard bestand opnieuw navragen, en dat zijn er nu meer. Achter nginx gebeurt dat niet (de bestanden zijn daar onveranderlijk en de service worker geeft ze uit zijn eigen voorraad), maar dat is niet gemeten.
9. **Mensen** haalt het hele inzetbord op (42 kB, 0,3 s) om per persoon te zeggen wanneer er ruimte komt. Een lichte vorm van het bord, zonder balken, zou volstaan.
10. **Het pictogrammenbestand van het designsysteem** is 168 kB (40 kB gzip) en komt in zijn geheel mee; grip gebruikt er enkele tientallen van. Dat is alleen in het designsysteem op te lossen.
11. **De kostenlijst** rekent voor elke pagina alle kostenposten door om te kunnen sorteren op wat aandacht vraagt.
12. **Vacatures en Inzet** hebben geen vensters; ze halen het budget en groeien met de geschiedenis.

## Niet gemeten

- Welke handelingen het slot op de stroom lang vasthouden (een aanlevering met een pdf, een offerte uitgeven). Het log zegt het sinds deze ronde; nagelopen is het niet.
- De lus voor meldingen met aangemelde apparaten, de mail-lus met een volle wachtrij, de outbox en inbox van de federatie, en de nachtelijke terugzetting van een voorbeeldinstantie.
- Meer dan een paar honderdduizend gebeurtenissen. De vragen aan de stroom lezen nu zoveel rijen als ze teruggeven, dus de verwachting is dat het niet uitmaakt; gemeten is het niet.
- Geheugen in bytes: de grens is een aantal waarden.
- De pagina's in een browser na deze ronde (`just check-speed`); gemeten zijn de verzoeken.

## De import uit Grist op deze grootte

Gemeten met een nagemaakt document: 155 mensen, 400 opdrachten, 2.046 begrotingsregels, 1.076 inzet, 300 kostenposten.

- `check` en `propose` duren minder dan een seconde.
- De bevestigingslijst telt 2.351 punten. `confirm --confidence hoog` handelt er 437 af; 1.545 begrotingsregels krijgen "laag", vooral omdat het bedrag niet gelijk is aan FTE maal tarief maal twaalf als een regel halverwege het jaar begint (de tabel heeft geen begin en einde). Dat is dagen handwerk in een JSON-bestand.
- De proefrun duurt 3 minuten, laden 3,5 minuut, een tweede keer laden 40 seconden; geheugen 230 MB.
- De tweede keer is niet helemaal "ongewijzigd": 22 regels met een regeleinde in de omschrijving worden opnieuw geschreven, en de eerste keer staat de tekst er dubbel in.
- Een omschrijving langer dan 500 tekens liet de import na 13 seconden vallen op een databasefout zonder rijnummer. Dat is nu een bevinding vooraf, met de rij; hetzelfde voor de naam en contactpersoon van een opdracht en het kenmerk van een factuurregel.
- Een soort factuurregel die niet in de koppeling staat ("Schatting") wordt met een waarschuwing als realisatie geladen. Een inschatting wordt zo gerealiseerd geld; loop die waarschuwingen na.
