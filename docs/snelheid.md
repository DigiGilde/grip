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
| JavaScript bij de eerste pagina (gzip) | 702 kB | 495 kB |

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

## Wat nog boven het budget zit

In volgorde van wat het de gebruiker kost.

1. **De eerste lezer na een wijziging die alle opdrachten raakt** (een tarief, een inzetschaal, een kostenpost of factuurregel, een persoon) en na een herstart: de startpagina 3 s, Factureren 7 tot 13 s, Rapportage 4 s. Factureren leest per opdracht nog rond de 20 statements als niets onthouden is; ook op de eerste dag van een maand. Oplossing: de leesfuncties van `billing_deliveries.overview` samen laten lezen, en kostengebeurtenissen alleen laten tellen voor de opdrachten die de kostenpost dekken.
2. **Vacatures**: `/api/tasks/courses` voor vacatures doet 2.040 statements en 1,3 s, bij elke keer laden. Het leest per vacature de teksten, de rondes en het formulier (`tasks/cases.py`).
3. **De taakmotor na een wijziging**: de eerste lezer van Taken of van de teller betaalt 1 s en ruim 1.000 statements, om dezelfde reden als punt 2.
4. `/api/reports/investment`: 0,3 tot 0,8 s en 263 statements, per opdracht geprijsd.
5. `/api/reports/steering`: 0,5 s; de bezetting van 150 mensen wordt elke keer berekend en het antwoord is 790 kB ongecomprimeerd.
6. `/api/allocations/board`: 0,3 tot 0,5 s en tot 72 statements; `/api/people` tot 0,4 s.
7. `/api/tasks/mine` en `/api/tasks/count`: 85 statements, toegang per taak op een vacature.
8. De eigen code is één bestand van 660 kB (188 kB gzip); de pagina's worden niet per route geladen.
9. Lijsten zonder vensters op de server: Opdrachten (216 kB voor 400), Kosten (366 kB), Team. Ze halen het budget nu, en groeien met de geschiedenis.

## Niet gemeten

- Meerdere schrijvers tegelijk op de stroom (één slot per transactie), en het loggen van inzagen onder belasting.
- De lussen van de worker (outbox, mail, push, bewaartermijnen) en de nachtelijke taken op deze grootte.
- De activiteitenpagina verder dan de eerste bladzijde, en het nieuws voorbij 800 gebeurtenissen.
- Geheugen van de server bij een volle cache (begrensd op 20.000 waarden, niet op bytes).
- Meerdere serverprocessen: elk heeft zijn eigen geheugen en betaalt punt 1 zelf.

## De import uit Grist op deze grootte

Gemeten met een nagemaakt document: 155 mensen, 400 opdrachten, 2.046 begrotingsregels, 1.076 inzet, 300 kostenposten.

- `check` en `propose` duren minder dan een seconde.
- De bevestigingslijst telt 2.351 punten. `confirm --confidence hoog` handelt er 437 af; 1.545 begrotingsregels krijgen "laag", vooral omdat het bedrag niet gelijk is aan FTE maal tarief maal twaalf als een regel halverwege het jaar begint (de tabel heeft geen begin en einde). Dat is dagen handwerk in een JSON-bestand.
- De proefrun duurt 3 minuten, laden 3,5 minuut, een tweede keer laden 40 seconden; geheugen 230 MB.
- De tweede keer is niet helemaal "ongewijzigd": 22 regels met een regeleinde in de omschrijving worden opnieuw geschreven, en de eerste keer staat de tekst er dubbel in.
- Een omschrijving langer dan 500 tekens liet de import na 13 seconden vallen op een databasefout zonder rijnummer. Dat is nu een bevinding vooraf, met de rij; hetzelfde voor de naam en contactpersoon van een opdracht en het kenmerk van een factuurregel.
- Een soort factuurregel die niet in de koppeling staat ("Schatting") wordt met een waarschuwing als realisatie geladen. Een inschatting wordt zo gerealiseerd geld; loop die waarschuwingen na.
