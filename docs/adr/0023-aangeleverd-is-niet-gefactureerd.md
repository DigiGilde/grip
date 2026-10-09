# 0023 Aangeleverd is niet gefactureerd

Status: aanvaard (2026-10-08)

Vult aan: [0012 Factuurgegevens, geen facturen](0012-factuurgegevens-geen-facturen.md)

## Context

Grip verstuurt geen facturen (ADR 0012). Per afgesloten maand maakt het een export van factuurgegevens voor de financiële administratie.

De jaarrekening en het tabblad Financieel telden een bedrag als "gefactureerd" zodra die export bestond, en "nog te factureren" was gerealiseerd min geëxporteerd. Het scherm kon daardoor zeggen dat alles gefactureerd was terwijl er nog niets de deur uit was. Grip beweerde iets wat het niet kan weten.

## Besluit

Er zijn drie feiten. Elk heeft een eigen woord, en geen bedrag krijgt een woord dat meer zegt dan grip weet.

| Woord | Feit | Hoe grip het weet |
|---|---|---|
| Aangeleverd | De factuurgegevens van een afgesloten maand zijn geëxporteerd voor de financiële administratie | De export bestaat (`billing_export`) |
| Gefactureerd | Er is een factuur verstuurd | Iemand heeft het vastgelegd (`outgoing_invoice`) |
| Betaald | De factuur is voldaan | Grip weet het niet en zegt er niets over |

Daaruit volgen twee openstaande bedragen:

- Nog aan te leveren: de vastgestelde inzet van afgesloten maanden, geprijsd, min wat is aangeleverd.
- Nog te factureren: aangeleverd min gefactureerd.

Zolang er geen factuur is vastgelegd, gebruikt geen scherm, rapport of export in grip het woord "gefactureerd" voor een bedrag.

Vastleggen van een factuur:

- Op een of meer aanleveringen legt iemand het factuurnummer, de factuurdatum en het bedrag van de factuur vast. Grip bewaart wie dat deed en wanneer.
- Het bedrag is wat op de factuur staat. Grip vergelijkt het met het aangeleverde bedrag en toont een verschil. Een verschil houdt het vastleggen niet tegen.
- Een vastlegging is te corrigeren; de oude en de nieuwe waarden staan in de auditlog. Een vastlegging die er niet had moeten zijn wordt ingetrokken met een reden. De rij blijft staan en de maanden staan daarna weer als aangeleverd.
- Een aanlevering hoort bij hoogstens een factuur.
- De vastlegging heeft een bron: met de hand, of het financiële systeem. Nu is het altijd de hand. Het veld bestaat zodat het financiële systeem later de bron van dit feit kan worden zonder dat het model verandert.
- Vastleggen mag wie de opdracht beheert (eigenaar of manager) en de beheerder. Lezen volgt gegevensklasse B.

De aanlevering die voor een maand telt is de laatste export van de afsluiting die geldt. Wordt een maand heropend, dan telt haar aanlevering niet meer. Een factuur die erop was vastgelegd blijft een feit: de maand blijft gefactureerd, en het scherm zegt dat de factuur bij een eerdere aanlevering hoort.

Het bedrag van een factuur over meerdere maanden wordt over die maanden verdeeld naar verhouding van wat per maand is aangeleverd. Een maand hoort bij het jaar waarin ze valt. Zo tellen de cijfers per jaar op tot het factuurbedrag.

Het vastleggen en het intrekken geven een domeingebeurtenis: `invoice.recorded` en `invoice.withdrawn`.

## Gevolgen

- De term "factuur" was in grip gereserveerd voor de inkoopregel op een kostenpost (`invoice_line`). Daar komt de uitgaande factuur bij (`outgoing_invoice`): de vastlegging dat een factuur aan de opdrachtgever is verstuurd. In de interface heet de inkoopregel een factuurregel op een kostenpost en de uitgaande factuur een factuur.
- "Nog te factureren" betekent iets anders dan voorheen. Wat eerder zo heette, is nu "nog aan te leveren".
- De CSV met factuurgegevens verandert niet. Er staat niets in dat op een factuur wijst.
- Vastleggen is handwerk en kan achterlopen op de werkelijkheid. "Nog te factureren" betekent daarom: aangeleverd, en in grip nog geen factuur vastgelegd.
- "Meer gefactureerd dan aangeleverd" kan voorkomen, bij een afwijkend factuurbedrag of na het heropenen van een gefactureerde maand. Het scherm toont dat als afwijking.
- Voor betaald is ruimte gelaten en niets gebouwd. Het kan als feit op de vastgelegde factuur komen, met dezelfde bron, zonder de twee andere feiten te raken.
- Een takenlaag bovenop de gebeurtenissen kan "factuur versturen" als taak openen bij een aanlevering en sluiten bij `invoice.recorded`.
- Wie een factuur vastlegt is nu wie de opdracht beheert. Een aparte functie voor de financiële administratie bestaat niet; komt die er, dan is dit de plek waar ze haar recht krijgt.

## Later gewijzigd (2026-10-09)

De drie woorden zijn gebleven. Aangeleverd is sindsdien een feit met een ontvanger en een moment: een factuurverzoek per factuurperiode, gemaild of zelf doorgegeven (ADR 0039). De factuur wordt op de aanlevering vastgelegd, niet op een maand.
