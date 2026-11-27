# 0056 De kroniek van een opdracht als bron

Status: voorgesteld (2026-11-04)

Vult aan: [0028 Een stroom van gebeurtenissen als bron](0028-een-stroom-van-gebeurtenissen-als-bron.md)

## Context

ADR 0028 noemt de stroom de bron, maar de code maakte dat niet waar. De tabellen waren de bron en de stroom een verslag ernaast. Van een opdracht waren 6 van de 22 velden niet exact uit de stroom terug te halen, van een begrotingsregel 5 van de 18, en een ontvangen offerte liet geen eigen gebeurtenis achter. De volledigheidstest merkte dat niet: die kijkt of er een gebeurtenis is, niet wat erin staat. Grip kon daardoor niet zeggen hoe een offertetraject er op een eerder moment voorstond.

Chronolexografie, een conceptueel model van de denktank Achterkant van de Overheid, beschrijft hoe je een rechtstoestand vastlegt: niet "de offerte is getekend", maar "op dit moment stelde deze partij vast dat ...". Een vastlegging heet een chronolexogram. Ze staat in een kroniek, in de cel die haar maakte. Een toestand is een reductie: ze wordt afgeleid, op verzoek, uit wat de cel heeft vastgelegd. RegelRecht heeft daarvan een voorbeeldimplementatie.

Grip is een proefopstelling zonder productiegegevens. De kosten van een ombouw wegen daarom niet mee.

## Besluit

**Op het pad naar een opdracht is een feit de bron.** Begroting, offerte, interne goedkeuring, aanbieden, akkoord en starten leggen elke handeling vast als één feit in de kroniek van de opdracht. De tabellen `assignment`, `assignment_role`, `budget_line`, `quote`, `quote_invitation`, `quote_offer`, `quote_approval`, `quote_acceptance` en `quote_rejection` zijn leesmodellen: ze worden alleen geschreven door een feit te vertalen.

**Eén functie zegt wat een feit doet.** `grip.chronicle.facts` geeft bij elk feit de effecten op de rijen, als gewone waarden, en leest daarvoor alleen de velden van het feit. Wat op het moment van vastleggen is besloten (welke offertes vervallen, welke regels meeschuiven) staat in het feit, zodat niets opnieuw wordt besloten. Dezelfde effecten vullen de tabellen in de transactie van het feit, en vouwen in het geheugen de stand op elk eerder moment op.

**Eén rij in de stroom.** Een feit is een gebeurtenis met onderwerp `chronolexogram`. De ene stroom van ADR 0028 blijft, met haar volgorde, keten, onveranderlijkheid en afdrukken. De bestaande wijzigingsregels en domeingebeurtenissen blijven ernaast bestaan, zodat alles wat ze leest blijft werken.

**Wie vaststelde staat in de vorm van het feit.** Een medewerker die vastlegt dat de opdrachtgever een pdf tekende is een ander feit dan iemand die via de tekenlink tekent. Een akkoord dat van een andere instantie binnenkomt draagt waar het vandaan kwam (`received`, met de naam van de afzender) en is hier geen besluit maar de vastlegging van een besluit elders. Dat geldt ook voor een afwijzing die iemand voor een ander noteert; wie zelf tekent of afwijst, via de tekenlink of als opdrachtgever in dezelfde instantie, besluit. Het scherm schrijft het feit in die vorm uit (`grip.chronicle.words`).

**Twee tijden.** `occurred_at` is wanneer iets is vastgelegd. `effective_on` is de dag waarop het telt, als die kan afwijken. Een snede op een positie zegt wat toen bekend was. Getekend op dag 3, vastgelegd op dag 10: de stand van dag 5 zegt dat er nog geen akkoord bekend is, en meldt daaronder dat later bleek dat het op dag 3 was getekend. Een correctie overschrijft niets: de eerdere stand houdt de eerdere datum, en de correctie staat in een stand naast de datum die zij corrigeert.

**De soort is een eigenschap van het feit.** Besluit (decretogram), uitvoering (executogram), regel (lexogram) of algemeen. Op het scherm staat alleen het merkteken "Besluit": de woorden uitvoering en regel betekenen in grip al iets anders.

**Tarieven hebben een eigen kroniek.** Tarievenkaarten blijven gewone tabellen. Elke keer dat wat prijst verandert, legt een feit het hele tarievenboek vast, zodat een stand wordt geprijsd met wat toen gold. Een concept prijst niets en laat geen feit na. Voor het eerste feit zijn er geen kaarten, en een stand van vóór dat feit prijst dus niets, zoals de live schermen toen.

**Terugkijken zonder een regel te herhalen.** De feiten van het verloop komen uit dezelfde pure functie als de live weergave (`assignment_snapshot`), het verloop uit dezelfde code (`views_of`), de bedragen uit `grip.calc`. Een stand is voor een lezer zonder aandeel in de zaak: "De eigenaar van de opdracht is aan zet: de offerte." Rechten zijn die van nu.

**Een veld heeft op elk moment de klasse die het live heeft.** Wie de naam van een regel mag lezen (klasse A), leest ook haar eerdere naam en de naam van een verwijderde regel; wie het FTE van een regel mag lezen (klasse C), leest ook het eerdere FTE. Het tabblad Wijzigingen is strenger: een wijziging van een regel zegt aan klasse A alleen dat ze gebeurde, niet van wat naar wat. Dat verschil is een keuze. Een stand volgt één regel, de klasse van het veld; het tabblad volgt er één per gebeurtenis. Uitzondering: de data, het akkoord en de goedkeuringen van een offerte nemen in een stand klasse B, ook waar een live route ze als A geeft; `effective_on` en `quote_date` horen daarbij. Wat rond de zaak veranderde staat in twee lijsten, `outside` (klasse A, zonder bedrag of dag) en `outside_values` (klasse B), omdat één veld geen twee klassen kan hebben.

**Namen, adressen en getypte tekst staan in de rij, niet in het feit (2026-11-06).** Dat geldt voor een kolom die eenmalig wordt geschreven of die geen stand toont: wie tekende (naam, adres, functie, `jws`), het adres van een uitnodiging en van een aanbieding, de toelichting bij een goedkeuring, de reden van een afwijzing, de contactpersoon van de opdrachtgever, de beoogde persoon op een regel en de bytes van de offerte. Het feit houdt de sleutel zonder waarde, en een stand leest de waarde in de rij (`ROW_ONLY_COLUMNS` in `grip.chronicle.facts`). Wissen is dan die rij bijwerken, en de geschiedenis blijft kloppen: bedragen, status en verloop staan in het feit. Een feit wordt nooit verwijderd, maar draagt deze waarden ook niet. Voor deze kolommen is de rij de bron: `kroniek-check` ziet een wijziging met de hand niet, en `kroniek-herstel` zet ze niet terug. Een ondertekende verklaring, een pdf of een `jws` staat als bewijs ernaast; voor een notitie en een tekening via de directe tekenroute is er niets anders.

**Bewijs.** `python -m grip.chronicle.check` vergelijkt de rijen van elke opdracht met haar kroniek. Het leest alleen en draait op elke instantie, naast de controle van de keten. `grip.chronicle.verify` kan beschadigde rijen uit de kroniek herstellen; dat draait alleen lokaal. In de tests volgt `tests/chronicle/proof.py` elk verzoek door een testclient (`GRIP_RECONSTRUCTION`, de fixture `chronicle_proof`): een wacht faalt als iets een leesmodel schrijft zonder feit, en na elk verzoek moet de vouwing gelijk zijn aan de rijen.

## Gevolgen

- Een nieuwe schrijfplek op deze negen tabellen gaat via `grip.chronicle.writer.establish`. Binnen een verzoek meldt de wacht elke schrijfactie om de kroniek heen, en de test faalt. Buiten een verzoek (de werker, opdrachten op de commandoregel) ziet de test op de broncode alleen constructors van de modellen en losse Core-opdrachten, geen toewijzing aan een attribuut, geen `session.delete` en geen `text(...)`; de wacht zet daar alleen een merk, en de test vergelijkt de kroniek van die test dan niet meer. Dat deel houdt dus op nazien, niet op afdwingen. Migraties zijn van de brontest uitgezonderd.
- Een feit neemt het slot op de stroom voordat het zijn rijen leest. Een rij met een versieteller die intussen verschoof, of welke rij ook die intussen weg is, weigert het feit (409, niets geschreven). Een rij zonder versieteller neemt wat het feit zegt: het laatste feit wint en rijen en kroniek blijven gelijk. De controles van de service lopen vóór het slot, op wat het verzoek las. Dat verloren-wijzigingsprobleem bestond al en is hier niet opgelost.
- Eén handeling levert nu twee soorten regels: het feit, en de wijzigingsregel met de domeingebeurtenis erachteraan. Dat is dubbel, en dat noemde ADR 0028 juist een probleem. De oude regels kunnen later uit het feit worden afgeleid; dat is niet gedaan omdat veel lezers en tests op hun exacte vorm rusten.
- `merge_roles` schrijft één feit per geraakte opdracht, en een onaangekondigde inkomende offerte drie (opdracht, delen, offerte). Op het hoofdpad is het één feit per handeling.
- `merge_roles` hoogt nu per regel de versie op: een open formulier krijgt na het samenvoegen een conflict, dat de beheerder noemt die samenvoegde.
- Een rol hernoemen in de catalogus verandert de naam op de regel in de database, buiten de kroniek. De kroniek houdt de naam van toen; `verify` vergelijkt de verwijzing, niet de naam. Een stand houdt de oude naam, ook op een moment na de hernoeming, en kan dan een andere stap noemen dan live: live vergelijkt de nieuwe naam met de bevroren offerte en ziet een verschoven begroting, de stand niet.
- Het verwijderen van een persoon leegt verwijzingen in de database, ook buiten de kroniek. `verify` houdt daar rekening mee.
- Een feit bevat nog wel tekst die verandert en die een stand toont zoals ze toen was: de naam en de notities van de opdracht, de omschrijving van een regel, de reden bij een statuswijziging, de naam van een afzender. Daarnaast de ids van personen, ook in de vaste gegevens van elke gebeurtenis. `erase_person` bereikt een feit niet, want een feit draagt geen `person_id`. De bewaartermijn van ADR 0028 wist wel de waarden van een heel feit. Hij laat de tarievenfeiten en de wijzigingen van de instelling voor interne goedkeuring staan, omdat die geen persoonsgegevens bevatten en elke latere stand ze nodig heeft. Gewiste waarden van een feit van de zaak of van een inzet van de zaak maken de stand van dat moment en van elk later moment onvolledig: die noemt geen totaal, geen bedragen per regel en geen status, en geeft geen verloop. Is het tarievenfeit dat gold gewist, dan noemt de stand ook geen bedragen.
- Een opgeslagen domeingebeurtenis laat weg wat de rij al bevat: de ondertekenaar en de `jws` bij een akkoord, de inhoud bij een offerte, de reden bij een afwijzing of statuswijziging, naam en omschrijving bij een aanvraag. Een afhandelaar in de transactie krijgt ze wel, zodat de federatie hetzelfde bericht verstuurt.

### Wat een stand niet kan

- De regels draaien met de code van nu. De uitkomst van een besluit staat wel in het feit, en een offerte blijft haar eigen bytes.
- Namen van personen en organisaties, het kenmerk `Organisation.instance_uri` en de rechten worden gelezen zoals ze nu zijn.
- De woorden van een stand zijn de woorden van nu, over toen.
- Tijd is geen feit: dat een offerte verliep staat pas bij het eerstvolgende moment.
- Wat de andere instantie zag, is niet hier te reduceren. Dat is synthese.
- Een stand prijst zonder te weten wie is ingezet. Waar live geen bedrag gaf omdat voor iemand op een regel een inzetschaal ontbreekt, noemt de stand het bedrag van de regel.
- `allocation`, facturatie en vacatures zijn geen leesmodellen. Na de start zegt een stand daarom niet meer wie aan zet is.
- Een stand zegt wat de plan-regels vroegen, niet welke taak er werkelijk stond: het overnemen van een stap en het afvinken van een taak zitten niet in de kroniek.

## Later

- De wijzigingsregels op dit pad afleiden uit het feit, zodat er geen twee verslagen meer zijn.
- Wissen op verzoek van een persoon, ook in feiten.
- Een kroniek per soort zaak voor vacatures en facturatie.
- Een offerte of akkoord bij de bron controleren: RegelRecht noemt dat een open vraag, en de hash en de ondertekende verklaring zijn hier een antwoord op.

## Later gewijzigd (2026-11-25)

Wissen op verzoek van een persoon, hierboven nog als later werk genoemd, vervalt. Een zaak wordt bewaard tot haar termijn verloopt, en wordt dan vernietigd; een getypte tekst die er nooit in hoorde, gaat eruit met een herstelfeit (ADR 0057). Een dossier sluit met een feit, en wat Grip zelf sluit staat in de kroniek met Grip als wie vaststelde.
