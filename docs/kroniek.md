# De kroniek van een opdracht

Op het pad naar een opdracht legt grip elke handeling vast als één feit. De tabellen van dat pad worden uit die feiten afgeleid, en de stand op elk eerder moment ook. Het besluit staat in [ADR 0056](adr/0056-de-kroniek-van-een-opdracht-als-bron.md); dit document beschrijft hoe het werkt en hoe je het ziet.

## Zien hoe het werkt

Start grip lokaal met voorbeeldgegevens en maak een traject:

```
just kroniek-nieuw               # een nieuwe voorbeeldopdracht, interne goedkeuring aan
just kroniek-stap <opdracht-id>  # de volgende stap, als de juiste persoon
just kroniek-check               # klopt elke tabel met zijn kroniek?
just kroniek-herstel <id>        # schrijf de stand van de kroniek terug naar de rijen
```

`kroniek-nieuw`, `kroniek-stap` en `kroniek-herstel` schrijven en weigeren daarom op een instantie die geen voorbeeldgegevens mag hebben. `kroniek-check` leest alleen en draait overal (zie Controleren).

Je kunt elke stap ook gewoon in het scherm doen. Bij de opdracht staat op de tab Geschiedenis de keuze Toon: Momenten of Wijzigingen. Momenten is de lijst van momenten. Open je een moment, dan zie je wie wat vastlegde en hoe opdracht, begroting en offerte er toen voorstonden, met het verloop van de zaak: de stappen en wie aan zet was. Het adres bevat het moment (`?moment=<volgnummer>`), dus de terugknop werkt.

Verloop betekent in grip de stappen van een zaak (zie [ontwerp.md](ontwerp.md)). De lijst van feiten heet Momenten.

## Begrippen

| Chronolexografie | In de code | Op het scherm |
|---|---|---|
| Chronolexogram | een feit: `Gram`, stroomtype `chronolexogram.<feit>` | moment |
| Kroniek | de feiten van één opdracht, op volgnummer | Geschiedenis, Momenten |
| Cel | de instantie | |
| Reductie | `fold` | Stand op ... |
| Lexostatus | `Ledger` en de stand die de service daarvan maakt | Stand op ... |
| Decretogram | `kind = decretogram` | Besluit |
| Executogram | `kind = executogram` | |
| Lexogram | `kind = lexogram` | |

De kroniek van een opdracht is strikt genomen een selectie: de instantie heeft één stroom met één tijdas (ADR 0028). Daardoor kan een stand ook wat buiten de zaak ligt (tarieven, instellingen) op dezelfde positie afsnijden. Chronolexografie kent geen volgorde tussen kronieken; grip heeft die wel en gebruikt die alleen hiervoor.

Systeemwoorden staan niet op het scherm (zie [ontwerp.md](ontwerp.md)).

## Schrijven

Eén plek schrijft de negen leesmodellen: `grip.chronicle.writer.establish`.

```python
await establish(
    session,
    "quote_offered",
    assignment_id=assignment.id,
    actor=actor,
    fields={"assignment_id": assignment.id, "offer": row_of(QuoteOffer, ...), ...},
)
```

De volgorde in een service is altijd: controles, voorbereiden (kenmerk, canonieke vorm, pdf), `establish`, en daarna de wijzigingsregel en de domeingebeurtenis zoals die er altijd waren. Afhandelaars vinden dan de rijen.

- `row_of(Model, ...)` is een hele rij: elke kolom behalve `version`, `updated_at` en `created_at`. Een kolom die je weglaat krijgt haar standaardwaarde; heeft ze er geen en mag ze niet leeg zijn, dan weigert `row_of`.
- `changes_of(Model, ...)` is een deel van een rij.
- Beide brengen een waarde in de vorm die de kolom bewaart. Zo is de vouwing tekst voor tekst gelijk aan de rij. Een `float` weigert `normal` in elke kolom behalve een JSON-kolom (wat een andere instantie stuurde). Wie een `float` heeft, maakt er eerst een `Decimal` van.
- Sleutels zijn de attribuutnamen van het model: `detail` op een begrotingsregel, niet `description`.

Een nieuw feit voeg je toe in `grip.chronicle.facts`: de naam, de soort, de titel en de effecten. Effecten lezen alleen de velden, nooit de toestand. Wat besloten is, staat in het feit. Zet de naam ook in de lijst van `tests/chronicle/test_core.py`.

Eén feit per handeling: wat samen ontstaat wordt samen vastgelegd, zodat niemand een tussenstand ziet die niemand zag. Een offerte maken is één feit, inclusief de vervallen offertes en de status van de opdracht.

### Twee tegelijk

Een feit neemt eerst het slot op de stroom en leest daarna de rijen die het wijzigt of verwijdert, met een rijslot, voorbij wat de sessie al las. Wat daarna gebeurt hangt van de rij af:

- Een rij met een versieteller (`assignment` en `budget_line`) die intussen is verschoven, weigert het feit, en elke rij die intussen weg is ook. Er wordt niets geschreven en de route antwoordt 409: "Dit is intussen gewijzigd. Er is niets overschreven. Probeer het opnieuw." De federatie-app kent die afhandeling niet en antwoordt 500: haar afzender probeert opnieuw en krijgt dan het antwoord op wat er nu staat. Een 409 zou dat opnieuw proberen juist stoppen. In een inhaalronde blijft het bericht staan voor de volgende ronde.
- Een rij zonder versieteller (de andere zeven) neemt wat het feit zegt, ook als dat gelijk is aan wat de sessie las. Het laatste feit wint, en rijen en kroniek blijven gelijk.

De controles van de service lopen vóór het slot, op wat het verzoek las. Dat verloren-wijzigingsprobleem bestond al en is hier niet opgelost: twee personen die tegelijk beslissen op dezelfde toestand krijgen allebei hun feit, in volgorde.

Wie rijen schrijft voordat er een gebeurtenis is, neemt het slot op de stroom eerst (`stream.hold_head`). Anders wacht wie het slot heeft op zo'n rij, en wacht die rij op het slot; iedereen die in de rij voor het slot staat, kan dan het slachtoffer zijn. Dat doen een hernoemde rol (de vreemde sleutel zet de naam op de begrotingsregels) en inzet die erbij komt, verandert of een regel of opdracht volgt.

### Wat een feit bevat

| Veld | Betekenis |
|---|---|
| `kind` | Besluit, uitvoering, regel of algemeen. |
| `plan_version` | De versie van het plan die voor deze zaak gold. |
| `recorded_on` | De dag waarop het is vastgelegd, volgens de klok van de instantie. |
| `effective_on` | De dag waarop het telt, als die kan afwijken: getekend op, afgewezen op. |
| `basis` | De regel die is gewogen, waar dat kon: de tarievenkaarten bij een offerte, de instelling bij een verzoek om goedkeuring. |
| `fields` | Wat is vastgesteld. Alle waarden die de effecten nodig hebben, behalve wat alleen in de rij staat (zie hieronder). |

Namen, adressen en getypte tekst in een kolom die eenmalig wordt geschreven of die geen stand toont, staan alleen in de rij: `ROW_ONLY_COLUMNS` in `grip.chronicle.facts`. `establish` geeft de effecten de volle waarden, maar het feit in de stroom houdt de sleutel met de waarde `null`. `ChronicleRepository` zet de waarde van de rij terug als het een feit leest, dus vouwing, woorden en stand zien haar zoals de rij haar nu heeft. Een nieuwe kolom met tekst, bytes of JSON kiest: in die lijst, of in `STAYS_IN_A_FACT` in `tests/chronicle/test_core.py` met de reden. Zonder keuze faalt de test.

Daarnaast `refs` op de gebeurtenis (hashes van bewijs dat elders ligt), en de vaste gegevens van elke gebeurtenis: wie, wanneer, herkomst, keten. Alle gebeurtenissen van één transactie delen het moment van de transactie, dus ook het feit en wat erachteraan komt.

Een feit dat een andere instantie stuurde (een aanvraag, een offerte, een akkoord of afwijzing) draagt in `fields` ook `received`. Daarin staan het peer-id, het bericht-id en de naam van de afzender (`received_from`, de opdrachtgever bij een aanvraag, de opdrachtnemer bij een offerte). Titel en zin zeggen dan "ontvangen van ...". Een offerte, akkoord of afwijzing met een moment buiten de jaren 1900 tot en met 2199 wordt geweigerd (`federation/bridge/inbound.py`): aan de randen van de kalender loopt de dag op de kalender van de instantie over en komt een moment zonder tijdzone terug uit de database. Een inhaalronde legt die weigering vast bij het bericht en gaat door.

### Oudere feiten en nieuwe kolommen

Een feit wordt nooit herschreven, dus een feit van vóór een nieuwe kolom zegt er niets over. Dat betekent:

- Wat een feit toevoegt aan zijn velden lees je met `.get`, nooit als aanwezig.
- Een kolom die een feit niet noemt, leest als wat de kolom heeft als er niets is gezegd: haar standaardwaarde of leeg. Voor een stand (`_row` in `grip.services.chronicle`) is dat zo; een kolom zonder standaard die niet leeg mag zijn (zoals `name`, `status`, `issued_at`) voegt een migratie niet zonder waarde toe; een oudere stand kan daar nog steeds op breken.
- `verify.differences` vergelijkt alleen sleutels die de vouwing kent. Een kolom die jonger is dan het feit is dus geen verschil, en de controle zegt er niets over.
- Een feitnaam wordt nooit hernoemd of verwijderd. Een naam die niet meer in `FACTS` staat wordt bij het vouwen overgeslagen zonder melding, en de stand zegt dan ook niet dat hij onvolledig is. `test_a_fact_keeps_its_name_for_good` legt de lijst vast.
- Een kolom op een van de negen tabellen hernoem je niet zonder een manier om oudere feiten te blijven lezen: een hernoemde sleutel valt anders weg.
- Een datamigratie op deze tabellen schrijf je als feit, of je noemt haar een uitzondering (zoals `dev/fix_role_po.py`). De test op de broncode slaat `migrations` over, dus niets anders merkt haar op.

## Lezen

| Route | Antwoord |
|---|---|
| `GET /api/assignments/{id}/chronicle` | De momenten, oudste eerst. |
| `GET /api/assignments/{id}/chronicle/{seq}` | De stand op dat moment. Een `seq` die geen moment van deze opdracht is, geeft 404. |
| `POST /api/assignments/{id}/chronicle/{seq}/restate` | Een getypte tekst uit dat moment halen (zie hieronder). |

De service (`grip.services.chronicle`) maakt het antwoord; de route beslist alleen wie wat mag lezen.

Elk veld hoort bij een gegevensklasse en heeft in een stand de klasse die het live heeft, op elk moment: de titel van een moment is klasse A, de zin en de bedragen klasse B, rol en FTE klasse C. Rechten zijn die van nu. Eén uitzondering: de data, het akkoord en de goedkeuringen van een offerte nemen in een stand klasse B, ook waar een live route ze als A geeft. Een lezer met alleen klasse A ziet in een stand van een offerte dus status, kenmerk en wat er veranderde, niet haar data of goedkeuringen. Daarom zijn ook `effective_on` van een moment en van wat later is vastgelegd, en `quote_date` van de opdracht, klasse B. `occurred_at` blijft klasse A: dat is wanneer iets is vastgelegd.

- De titel zegt het feit in de vorm die het had: wie een getekende pdf vastlegt, staat bij "Getekende pdf vastgelegd", niet bij "Offerte getekend".
- `actor_kind` (klasse A) zegt of een persoon, een gast, een andere instantie of het systeem vaststelde, waar geen naam is.
- `outside` (klasse A) zegt zonder waarde wat er rond de zaak veranderde; `outside_values` (klasse B) zegt het met het bedrag en de dag en vervangt voor wie het krijgt `outside`. Voor klasse A zijn tarieven één regel, "De tarieven zijn gewijzigd.", hoeveel feiten er ook waren.
- Is de stand onvolledig, dan noemt hij geen totaal, geen bedragen per regel, geen vorig totaal en geen status ("Onbekend"), en geeft hij geen verloop.

Een feit is niet te lezen via `/api/events` voor wie geen beheerder is: het bevat waarden van meer klassen onder één sleutel. Het tabblad Wijzigingen is daarmee strenger dan een stand: een wijziging van een regel zegt aan klasse A alleen dat ze gebeurde. Een stand geeft die lezer de eerdere naam van een regel en de naam van een verwijderde regel, omdat de klasse van het veld op elk moment geldt (ADR 0056).

### Wat er in een stand gaat

Op positie N:

| Wat | Waar het vandaan komt |
|---|---|
| Opdracht, rollen, regels, offertes en wat erbij hoort | De vouwing van de feiten tot en met N |
| Tarieven | Het laatste `rates_established` tot en met het einde van die handeling. Is er nog geen, dan zijn er geen kaarten en prijst de stand niets: een concept laat geen feit na |
| Instelling voor interne goedkeuring | De laatste wijzigingsregel van die instelling tot en met dat punt |
| Inzet (alleen voor de vraag of een rol is ingevuld; er wordt zonder geprijsd) | De wijzigingsregels `allocation.*`, met de data van de regel als de inzet de regel volgt |
| Eindverslag (alleen of het is uitgegeven) | De wijzigingsregel `final_report` van de opdracht |
| Vandaag | `recorded_on` van het feit |
| Plan | `plan_version` van het feit |
| Rechten, namen, `Organisation.instance_uri` | Zoals het nu is |

Het feit is het eerste van zijn handeling: wijzigingsregels komen erna. Wat buiten de zaak ligt, wordt daarom gesneden aan het einde van de handeling: het hoogste volgnummer met hetzelfde correlatie-id én hetzelfde moment van de transactie, onder het volgende feit van de kroniek. Een correlatie-id alleen is niet genoeg: een aanroeper kan hem zelf kiezen (een traceparent) en zo meerdere verzoeken onder één id brengen.

Geen regel wordt herhaald. De feiten van het verloop komen uit `assignment_snapshot`, het verloop uit `course.at_moment` (dezelfde `views_of` als live), de bedragen uit `grip.calc`, en de vraag of de begroting verschoof uit `budget_fingerprint`.

## Een tekst die er nooit in hoorde

Een beheerder haalt in een moment een getypte tekst weg die er nooit in hoorde, zoals gegevens over iemands gezondheid in de notities (ADR 0057). Het kan gaan om de naam of de notities van de opdracht, de toelichting bij een mondeling akkoord, de omschrijving van een begrotingsregel en de reden bij een statuswijziging of een gecorrigeerde datum. De lijst staat op één plek: `TYPED_TEXTS` in `grip.chronicle.restate`, met het label per tekst. Wat alleen in de rij staat (`ROW_ONLY_COLUMNS`) hoort er niet bij: dat is de rij bijwerken.

De database wist alleen alle waarden van een gebeurtenis tegelijk, nooit één veld. Daarom doet `grip.services.restatements` in één transactie dit:

- Elk feit van de zaak waarin de tekst staat, krijgt een herstelfeit (`fact_restated`, op het scherm "Tekst verwijderd"): hetzelfde feit zonder de tekst. Dat geldt ook voor een herstelfeit zelf, als later nog een tekst uit hetzelfde moment gaat. Ook de naam van een regel in een later feit verliest zo de omschrijving.
- Een kolom die leeg mag zijn, wordt leeg. Een kolom die dat niet mag (de naam, de omschrijving) krijgt "Tekst verwijderd". Staat de tekst als woord of zin in een langere tekst, dan komt "Tekst verwijderd" op haar plaats. Een tekst van minder dan acht tekens (`MIN_EMBEDDED`) gaat alleen waar hij de hele waarde is: binnen een langere waarde is zo'n kort stukje te vaak toeval.
- Een herstelfeit telt niet als activiteit voor het dossier (`grip.services.dossiers.last_activity`): het herstelt de vastlegging, niet de zaak. Het wissen telt ook niet, en de wijzigingsregels die de rijen gelijk zetten schrijft Grip zelf. Dat hangt aan het soort gebeurtenis en aan wie haar schreef, nooit aan het correlatie-id: dat kiest een aanroeper zelf (`traceparent`).
- Het herstelfeit bevat het volgnummer en de naam van het feit dat het herstelt, de velden zonder de tekst, de soort, het plan en de dagen van dat feit, waar de tekst stond met het label (nooit de tekst), en de rijen die de tekst nog hebben (`patches`). Een rij krijgt alleen een patch als het laatste feit dat die kolom schreef een herstelde is; heeft een later feit de kolom al veranderd, dan blijft de rij zoals ze is. Het wordt geschreven met `establish`, zoals elk feit.
- Daarna worden de herstelde feiten gewist, en elke andere gebeurtenis van de zaak die de tekst als getypte tekst bevat: onder de sleutel van een naam, notities, toelichting, omschrijving of reden, of in de notitie van de gebeurtenis. Dat zijn vooral wijzigingsregels. Een gebeurtenis die de tekst alleen ergens anders noemt, houdt haar waarden: een besluit, een status of bewijs verdwijnt niet door een toevallige overeenkomst. Een feit wordt nooit alleen gewist. Wie op een regel staat (`allocation`) blijft staan: daar staat geen getypte tekst in, en een stand leest het.
- Niet geraakt: de bevroren inhoud van een uitgegeven offerte en wat al naar een andere organisatie is gestuurd. Staat de tekst in een offerte, dan zeggen het scherm en het antwoord dat.

Bij het lezen zet `ChronicleRepository` het herstelfeit op de plaats van het gewiste feit: zelfde positie, met de velden, de soort en de dagen uit het herstelfeit, en in `Gram.restated_by` welke herstelfeiten er een tekst uit haalden. Het leest de herstelfeiten ook voorbij de snede, dus een stand van vóór het herstelfeit is ook heel. Het herstelfeit zelf vouwt als zijn patches; na de vervanging verandert dat niets meer. De vouwing blijft puur (`grip.chronicle.restate.substituted`). Zo blijven de stand van het herstelde moment en elke latere stand compleet, en vergelijken `differences` en `kroniek-check` gewoon verder.

`POST /api/assignments/{id}/chronicle/{seq}/restate` krijgt `{"columns": [...]}`, de sleutels uit `TYPED_TEXTS`, en antwoordt met de stand van dat moment (`stand`) en de offertes die de tekst houden (`kept`). Alleen de beheerder mag het (`restate_fact`). Een `seq` die geen moment van deze opdracht is, of een moment dat gewist is zonder herstelfeit, geeft 404; een sleutel zonder tekst in dat moment geeft 422 met een zin.

Een stand noemt in `restated` de herstelfeiten die later een tekst uit dat moment haalden, met de labels; het herstelfeit is een eigen moment in de lijst. Alleen wie een tekst mag weghalen, krijgt in een stand `removable_texts`: per tekst de sleutel, het label, de tekst en de offertes waarin ze ook staat. Voor ieder ander is dat veld leeg.

Een omschrijving die ook in een uitgegeven offerte staat, wijkt daarna af van die offerte. Zolang die offerte openstaat, zegt het verloop dan dat de offerte niet meer bij de begroting past, live en in een stand van na de offerte.

## Controleren

Er zijn twee dingen, voor twee plekken.

`python -m grip.chronicle.check` (`just kroniek-check`) leest alleen en draait op elke instantie, naast `python -m grip.events.check` voor de keten. Het vergelijkt elke opdracht met haar kroniek, drukt per opdracht af wat verschilt, noemt per reden wat het oversloeg, en eindigt met code 1 bij een verschil. Overslaan is geen verschil: een opdracht zonder kroniek, zonder geboortefeit, met gewiste waarden of die zelf weg is, wordt geteld en genoemd. Een opdracht die niet te lezen is, wordt genoemd en geteld als niet te controleren; de rest gaat door en het eindigt ook dan met code 1.

```python
report = await verify.differences(session, assignment_id)
```

`differences` is wat daaronder zit: het vergelijkt de vouwing met de rijen, langs de sessie heen. Niet vergeleken: `version`, `updated_at`, `created_at` en de naam van de rol op een regel (de verwijzing wel), en een sleutel die de vouwing niet kent. Een kolom uit `ROW_ONLY_COLUMNS` is in de vouwing de waarde van de rij, dus een wijziging daarvan met de hand is geen verschil.

`rebuild` schrijft de vouwing terug en legt dat zelf vast (`chronicle_rebuilt`). Het schrijft de eigenaar als laatste, zodat de oude eigenaar eerst terugtreedt. Dat is het bewijs dat de tabellen afgeleid zijn: beschadig een rij en de kroniek zet haar terug. Het draait alleen lokaal, via `just kroniek-herstel`. Of het ook op een echte instantie mag, is niet besloten.

### In de tests

`tests/chronicle/proof.py` volgt elk verzoek door een testclient (de fixture `chronicle_proof`, met `grip.chronicle.guard`):

- Een schrijfactie op een leesmodel binnen een verzoek zonder feit laat de test falen.
- Na elk verzoek moet `differences` leeg zijn voor de opdrachten waar het verzoek een feit over schreef.
- Zet een test zelf rijen klaar buiten een verzoek, dan worden de kronieken in die test niet vergeleken.
- `GRIP_RECONSTRUCTION` kiest wat er gebeurt: `verify` (standaard) laat de test falen, `report` voegt de bevindingen toe aan het bestand uit `GRIP_RECONSTRUCTION_REPORT`, `off` volgt niets.

Een test op de broncode (`tests/chronicle/test_read_models_only.py`) eist dat niets buiten `grip.chronicle` deze negen modellen aanmaakt of met een losse Core-opdracht (`update`, `insert`, `delete`) wijzigt. Een toewijzing aan een attribuut, `session.delete` of een `text(...)` ziet hij niet; buiten een verzoek (de werker, opdrachten op de commandoregel) houdt dat deel dus op nazien. `dev/fix_role_po.py` is de bekende uitzondering.

## Wat een stand niet kan

Zie de gevolgen in [ADR 0056](adr/0056-de-kroniek-van-een-opdracht-als-bron.md).
