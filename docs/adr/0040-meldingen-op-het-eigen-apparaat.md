# 0040 Meldingen op het eigen apparaat

Status: aanvaard (2026-10-08)

Vult aan: [0024 Taken](0024-taken-feiten-en-het-plan.md), [0028 Een stroom van gebeurtenissen als bron](0028-een-stroom-van-gebeurtenissen-als-bron.md), [0031 De tekenlink gaat per mail](0031-tekenlink-per-mail.md), [0037 Passkeys, en grip als installeerbare applicatie](0037-passkeys-en-een-installeerbare-applicatie.md)

## Context

Grip weet wat er op iemand wacht: de takenlaag zegt per persoon welke taken van die persoon zijn om te doen. Wie grip niet open heeft, merkt daar niets van. Een geinstalleerde webapplicatie kan een melding tonen op het apparaat van de persoon (web push).

Een melding onderbreekt iemand, op een vergrendeld scherm, waar een ander kan meelezen. Dat bepaalt wat erin mag staan en hoe vaak ze mag komen.

## Besluit

### Waarover

Een melding is er voor "er wacht nu iets op jou" en voor niets anders:

- **een taak wordt van jou om te doen.** Niet een taak waar je alleen op wacht. Een gevraagde interne goedkeuring is zo'n taak.
- **een taak van jou is over de datum,** een keer.
- **er is beslist over iets dat jij aanbood:** een offerte is getekend of afgewezen (voor de eigenaar en de managers van de opdracht), een interne goedkeuring is gegeven of teruggestuurd (voor wie haar vroeg). Dat wil iemand snel weten.

Voor een gewone wijziging komt geen melding.

### Wat erin staat

Een melding bevat geen zin en geen naam. De server stuurt een soort uit een vaste lijst, een aantal, een pad met alleen id's en een nietszeggend id. De service worker kiest de woorden uit zijn eigen vaste lijst ("3 taken wachten op je", "Een offerte is getekend") en haalt niets op om een melding te tonen. Zo kan er op een vergrendeld scherm nooit een naam van een persoon, een opdrachtgever of een bedrag staan, ook niet door een fout aan de serverkant.

De inhoud is onderweg versleuteld voor die ene browser (RFC 8291); de dienst van de browserleverancier die haar doorgeeft kan haar niet lezen. Dat verandert niets aan het vergrendelde scherm, en daarom blijft de inhoud zo kaal. Rijkere inhoud is geen instelling: wie meer wil weten opent grip, waar is ingelogd en het toegangsmodel beslist.

### Niet te veel

- Taken die kort na elkaar openen worden een melding (`PUSH_BATCH_SECONDS`).
- Per soort staat er hooguit een melding op het apparaat: een nieuwe vervangt de oude.
- Stille uren en het weekend, per persoon in te stellen. Wat in die tijd ontstaat, komt daarna als een melding.
- Een maximum per dag (`PUSH_DAILY_CAP`).
- Geen melding voor wat je zelf veroorzaakte, en geen melding voor wat al op je wachtte toen je je eerste apparaat aanmeldde.
- Per soort uit te zetten.

Het getal op het pictogram van de applicatie is het aantal taken dat van jou is om te doen, hetzelfde getal als in de navigatie.

Een melding intrekken zodra de taak dicht is, zonder dat de persoon iets ziet, kan niet betrouwbaar: een browser eist dat elke push iets toont. Grip ruimt daarom op waar het kan: opent de persoon grip en wacht er niets meer, dan verdwijnen de meldingen over taken en het getal.

### Toestemming

Grip vraagt de browser nooit uit zichzelf om toestemming. De persoon zet meldingen aan met een knop, op de pagina Meldingen of bij de taken, na een zin over wat er komt en hoe vaak. Pas dan vraagt de browser. Weigert de persoon, dan zegt de pagina een keer waar dat is terug te draaien. Op een iPhone of iPad werkt het alleen vanaf het beginscherm; dat staat er dan.

Een persoon heeft meerdere apparaten en beheert alleen de eigen. Uitloggen meldt het apparaat af.

### Hoe het loopt

- Niets in de takenlaag of het domein roept dit aan. De worker stelt per persoon met een apparaat de vraag die het scherm ook stelt (`to_do_of`) en vergelijkt met wat die persoon al gemeld kreeg. Beslissingen leest hij uit de stroom van gebeurtenissen, met een cursor.
- Versturen gaat via een wachtrij met herhaalpogingen, zoals de mail, met een eigen tabel.
- Een apparaat dat de dienst van de browserleverancier niet meer kent (404 of 410) wordt verwijderd.
- Het protocol (RFC 8030, 8291, 8292) is geschreven met wat grip al had, `cryptography` en `httpx`. Er is geen bibliotheek bijgekomen en niets van een leverancier.
- Zonder sleutelpaar (`PUSH_VAPID_PRIVATE_KEY`) staat het uit en werkt al het andere.

### Een voorkeur voor meldingen en mail

Hoe iemand verteld wil worden dat er iets wacht, is een voorkeur per persoon: meldingen op het apparaat, een samenvatting per mail, allebei of geen. De samenvatting per mail wordt nog niet verstuurd; de keuze wordt al bewaard, zodat de twee later niet dubbel lopen.

## Gevolgen

- Migratie `0033_push`: apparaten, de voorkeur, de wachtrij, wat al gemeld is, en de cursor.
- Het platform levert een geheim (het sleutelpaar) en moet uitgaand https toestaan naar de diensten van de browserleveranciers. Zie [meldingen.md](../meldingen.md).
- Een ander sleutelpaar beeindigt alle aanmeldingen: mensen zetten meldingen dan opnieuw aan.
- De worker moet draaien; zonder worker wordt er niets gemeld.
