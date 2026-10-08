# Import uit Grist

Dit is de werkwijze voor wie de gegevens uit het Grist-document naar grip overzet. De import is herhaalbaar: je draait hem zo vaak als nodig tot de overstap, en elke run werkt bij wat er al staat.

## Stand van zaken

De import is gebouwd en getest op een nagemaakt document met verzonnen gegevens. Het echte document is nog niet gelezen. Daardoor is een deel onbevestigd:

| Onderdeel | Stand |
|---|---|
| Bestandsvorm van een Grist-download | Bevestigd aan de broncode van Grist (zie onderaan) |
| Tabel- en kolomnamen in `mapping.toml` | Afgeleid uit beschrijvingen van het document, niet uit het document zelf |
| Statussen van een opdracht en soorten factuurregel | Afgeleid, zelfde voorbehoud |
| De formules achter de rekenregels | Onbekend tot `inspect` op het echte document is gedraaid |
| Hoe schaal, rol, FTE en start in vrije tekst staan | De herkenning is geschreven op voorbeelden uit de beschrijving |

De eerste twee stappen hieronder lossen dat op.

## Wat je nodig hebt

- Een download van het Grist-document. In Grist: Delen, Exporteren, Download. Het bestand eindigt op `.grist` en is een SQLite-database.
- Een draaiende grip met een lege of eerder geïmporteerde database, en de migraties bijgewerkt (`just migrate`).
- Een map buiten de repository voor de download, de bevestigingslijst en de rapporten. Deze bestanden bevatten namen en bedragen en horen niet in git.

Alle stappen draai je met `just import-grist`. De eerste vier raken de database niet.

## Stap 1: bekijk wat er in het document zit

```
just import-grist inspect ../import/document.grist
```

Dit toont elke tabel met het aantal rijen, elke kolom met zijn type, en elke formule voluit. Daarna volgt het oordeel over vier formules die een open vraag beslissen, en de uitkomst van de controle van de koppeling.

De uitvoer bevat alleen structuur, geen inhoud van cellen. Je kunt hem dus delen met wie de koppeling afmaakt.

Het oordeel over de formules lees je zo:

| Regel | Vraag | Mogelijke uitkomst |
|---|---|---|
| R2 | Hoe worden gedeeltelijke maanden geprijsd? | `grist_datedif`, `whole_months` of `calendar_days` |
| R6 | Telt de prognose realisatie en inschatting op? | `both` of `subset` |
| R7 | Gaat dekking over prognose of over begroot? | `forecast` of `budgeted` |
| R4 | Is Begroot ingevoerd of berekend? | `entered` of `computed` |

Staat er "niet herkend", dan staat de formule eronder. Lees haar en leg de uitkomst vast; de aansluiting in stap 6 toetst hetzelfde nog eens op de cijfers.

## Stap 2: maak de koppeling passend

De koppeling staat in `backend/grip/importers/grist/mapping.toml`. Per tabel staat daar het tabel-id in Grist, en per veld het kolom-id.

```
just import-grist check ../import/document.grist
```

De controle meldt alles in een keer:

- **fout**: een tabel of een verplichte kolom die niet in het document staat. Pas het id aan in `mapping.toml`.
- **waarschuwing**: een kolom die mag ontbreken, of een tabel die nog op `verified = false` staat.
- **info**: een kolom of tabel in het document die niet gekoppeld is en dus niet wordt gelezen. Loop deze lijst na: staat er iets tussen dat mee moet, dan ontbreekt er een veld in de koppeling.

Draai `check` opnieuw tot er geen fouten meer zijn. Zet dan per tabel `verified = true`. Zolang een gebruikte tabel onbevestigd is, weigert de import te laden.

Onder `[values.status]` staat welke status in Grist welke status in grip wordt. Controleer die lijst tegen de keuzes in het document.

Wil je de meegeleverde koppeling niet wijzigen, kopieer haar dan en geef `--mapping pad/naar/eigen.toml` mee aan elke opdracht.

## Stap 3: laat voorstellen maken voor de vrije tekst

```
just import-grist propose ../import/document.grist --confirmations ../import/bevestiging.json
```

Dit schrijft de bevestigingslijst. Daarin staat een item voor alles wat de import moest interpreteren:

| Soort | Wat je beoordeelt |
|---|---|
| `person` | Is deze rij een echte persoon, en wat is het e-mailadres? Een naam als "Developer #3" wordt voorgesteld om over te slaan. |
| `person_scale` | De inzetschaal, gelezen uit de kolom en de notitie. Bij "Schaal 11, maar rekent met 12" is het voorstel 12. De salarisschaal wordt niet opgeslagen. |
| `budget_line` | Is de regel personeel of een vaste post? Voor personeel: rol, FTE, tariefcategorie, begin en einde. |

Elk item toont de oorspronkelijke tekst (`source`), het voorstel (`proposal`), de zekerheid (`hoog`, `middel`, `laag`) en opmerkingen. Onder `values` staat wat er geladen wordt; daar pas je aan.

Zo werk je de lijst af:

1. Open `bevestiging.json` in een editor.
2. Zet per item `status` op `bevestigd` als `values` klopt, na verbeteren waar nodig. Zet `status` op `overslaan` als het item niet mee moet.
3. Laat `proposal` en `source` ongemoeid.

Items met zekerheid `hoog` kun je in een keer bevestigen, nadat je er een aantal hebt nagekeken:

```
just import-grist confirm ../import/bevestiging.json --confidence hoog
```

Waar je op let:

- **E-mailadressen.** Staat er geen adres in Grist, vul het dan in. Iemand logt in grip in met het adres waarop hij bekend is; zonder adres krijgt de persoon een plaatshouder en kan hij niet inloggen.
- **FTE afgeleid uit het bedrag.** Noemt een omschrijving geen FTE, dan rekent de import terug vanuit Begroot. Dat staat in de opmerking.
- **"Begroot wijkt af".** De omschrijving en het bedrag spreken elkaar tegen. Beslis welke klopt.
- **Zekerheid laag.** Hier is de tekst niet of half gelezen. Vul `values` zelf in.

Er wordt niets toegepast dat niet bevestigd is.

## Stap 4: proefrun

```
just import-grist load ../import/document.grist --confirmations ../import/bevestiging.json --dry-run
```

Een proefrun doet alles, inclusief de aansluiting, en draait daarna alles terug. Je ziet:

- wat er uit het document is gelezen, met bevindingen;
- wat er nieuw, gewijzigd en ongewijzigd zou zijn;
- het aansluitrapport.

De import stopt vooraf, zonder iets te schrijven, als de koppeling onbevestigd is, als er nog items op `voorstel` staan, of als het document fouten bevat. Los ze op en draai opnieuw.

Met `--allow-unconfirmed` ga je door terwijl er items openstaan. Onbevestigde begrotingsregels worden dan als vast bedrag geladen met hun oorspronkelijke tekst, hun inzet wordt niet geladen en schalen blijven leeg. Dat is bedoeld om alvast te kijken, niet voor de overstap.

## Stap 5: laden

```
just import-grist load ../import/document.grist --confirmations ../import/bevestiging.json --actor-email jij@voorbeeld.example
```

`--actor-email` is het adres van een persoon in grip. Die staat dan als bron in de auditlog. Zonder deze optie staat het systeem er als bron.

De import schrijft in een transactie. Weigert grip ook maar een onderdeel, dan wordt er niets vastgelegd en staat de reden per rij in de uitvoer.

De import gebruikt dezelfde regels als de schermen. Wat een scherm weigert, weigert de import ook: dekking boven 100 procent, een einddatum voor een begindatum, een wijziging in een gesloten tariefjaar. Voor dat laatste bestaat `--allow-closed-year`; elke wijziging laat dan een auditregel achter.

Uitkomstcodes: 0 is geladen en aangesloten, 1 is fouten en niets geschreven, 2 is verkeerd gebruik of onleesbare invoer, 3 is geladen maar de aansluiting toont verschillen.

## Stap 6: lees het aansluitrapport

Het rapport zet per opdracht, begrotingsregel, inzet, kostenpost en KPI het bedrag uit Grist naast wat grip berekent. Gelijk betekent minder dan een halve euro verschil.

Twee rekenkeuzes staan nog open: hoe een gedeeltelijke maand wordt geprijsd, en of dekking over de prognose of over het begrote bedrag gaat. Het rapport rekent daarom alle zes combinaties door en zegt welke het best aansluit.

- Is de best aansluitende combinatie niet de standaard van grip, dan zegt het rapport dat. Leg dat besluit vast en laat de standaard aanpassen voordat de cijfers in grip gelden. Tot dan rekenen de schermen met de oude standaard.
- Onder "Afwijkingen" staat elke waarde die niet aansluit, met een opmerking als grip niet kon rekenen.

Veelvoorkomende opmerkingen:

| Opmerking | Wat te doen |
|---|---|
| geen actieve tarievenkaart voor een jaar | Inzet loopt door in een jaar zonder tarieven. Maak de kaart aan onder Tarieven en sluit opnieuw aan. |
| de persoon heeft geen inzetschaal | De schaal van die persoon is niet bevestigd. Werk de bevestigingslijst bij. |
| regel is niet bevestigd | De regel is als vast bedrag geladen. |
| Inzet van een overgeslagen persoon | Het bedrag telt in Grist mee in de uitputting en in grip niet. Dit verschil is verklaard. |

Opnieuw aansluiten zonder te laden, bijvoorbeeld nadat je een tarievenkaart hebt toegevoegd:

```
just import-grist reconcile ../import/document.grist --confirmations ../import/bevestiging.json
```

Met `--report pad` schrijf je het rapport ook naar een bestand, met `--all-rows` toon je alle vergeleken waarden.

Staat er "Uitkomst: NIET AANGETOOND", dan noemt de koppeling geen kolommen met berekende bedragen. Vul die in bij de velden `budgeted`, `used`, `available`, `forecast`, `covered` en de KPI-velden.

## Stap 7: herhaal tot de overstap

Bij een nieuwere download:

1. Draai `propose` met dezelfde bevestigingslijst. Beslissingen blijven staan zolang de brontekst niet is gewijzigd. Is die wel gewijzigd, dan gaat het item terug naar `voorstel` en staat je vorige keuze erbij.
2. Draai de proefrun en daarna `load`.

De import onthoudt per Grist-rij wat er in grip van gemaakt is. Een rij die al geladen is wordt bijgewerkt, niet opnieuw aangemaakt. Houd `--document-key` gelijk tussen runs; laat je de optie weg, dan is dat vanzelf zo.

De import verwijdert nooit iets. Een rij die uit Grist is verdwenen wordt gemeld; beoordeel in grip of het bijbehorende gegeven weg moet.

Schaalhistorie wordt niet overschreven. Verandert een schaal tussen twee runs, dan meldt de import dat en pas je het aan in het scherm Team.

## Stap 8: overstap

1. Spreek een moment af waarna niemand meer in Grist wijzigt.
2. Maak een laatste download, draai `propose`, de proefrun en `load`.
3. Het aansluitrapport moet "SLUIT AAN" zeggen, of elk verschil moet verklaard zijn.
4. Zet het Grist-document op alleen-lezen.
5. Bewaar de download, de bevestigingslijst en het rapport bij elkaar als bewijs van de overstap.

## Wat de import niet doet

- **Offertedatum.** Die komt in de notitie van de opdracht; er is geen eigen veld dat de import mag vullen.
- **Opdrachtgever als organisatie.** Grist heeft alleen een contactpersoon. De organisatie koppel je in grip.
- **Kostprijs en marge van inhuur.** Staat een inhuurkracht in Grist als kostenpost, dan blijft het een kostenpost.
- **Afgesloten maanden.** Na de import is elke maand open; uitputting is dus planning tot je in grip maanden afsluit.
- **Opdrachten over de jaargrens.** Opdrachten die in Grist per jaar zijn geknipt blijven zo.
- **Twee rijen dekking voor dezelfde kostenpost en regel** worden een aandeel; de percentages tellen op.

## Bestandsvorm, en waar dat op berust

Bevestigd aan de broncode van Grist (grist-core: `DocStorage.ts`, `schema.py`, `usertypes.py`, `moment.py` en `GristData.ts`):

- Een document is een SQLite-bestand. Elke gebruikerstabel is een SQL-tabel met het tabel-id als naam, de kolom-id's als kolommen, en een rij-id in `id`.
- `_grist_Tables` heeft `tableId`. `_grist_Tables_column` heeft `parentId`, `colId`, `type`, `isFormula`, `formula` en `label`.
- De uitkomst van een formulekolom staat in het bestand, naast de formule zelf. Daardoor kan de import de bedragen van Grist lezen zonder ze na te rekenen.
- Een verwijzing is een rij-id als geheel getal. Een lijst van verwijzingen of keuzes staat als JSON in een tekstcel.
- Een datum is het aantal seconden sinds 1 januari 1970, middernacht UTC.
- Een waarde die niet in het kolomtype past staat als binaire waarde in Python-marshalformaat. Een formulefout is zo'n waarde: een lijst die begint met de letter E. De import leest van dat formaat een kleine, veilige deelverzameling en voert niets uit.

Niet bevestigd:

- Of de Grist-versie waar het document in staat dezelfde opslagvorm gebruikt als de broncode van nu. De import leest alleen de kolommen hierboven en meldt het als de metadata-tabellen ontbreken.
- Alles wat over het document zelf gaat: zie de tabel bovenaan.
