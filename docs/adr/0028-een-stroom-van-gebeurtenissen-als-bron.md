# 0028 Een stroom van gebeurtenissen als bron

Status: aanvaard (2026-10-08)

## Context

Grip legde op twee manieren vast wat er gebeurde. De auditlog schreef per wijziging wie wat veranderde, met de oude en de nieuwe waarde. Daarnaast riep de servicelaag domeingebeurtenissen uit ("offerte aanvaard", "status gewijzigd"), waar de federatiemodule en de takenlaag op reageren. Die gebeurtenissen bestonden alleen in het geheugen van het proces.

Dat zijn twee gedeeltelijke verslagen van hetzelfde, apart geschreven. Ze kunnen van elkaar afwijken, en geen van beide beantwoordt de vraag "wat is er met deze opdracht gebeurd" volledig. De auditlog kende geen zaak, geen gast en geen andere instantie als actor, en zei niets over wie gegevens inzag. Niets maakte zichtbaar dat een regel achteraf was aangepast of verwijderd.

## Besluit

Er is één duurzame stroom van gebeurtenissen. Alles wat in een instantie gebeurt, staat erin, in de volgorde waarin het vaststond. De auditlog is een blik op die stroom, en alles wat reageert wordt eruit gevoed.

**Eén record.** Een gebeurtenis heeft een volgnummer en een id, een tijd, een type met een vaste naam (`quote.accepted`, `budget_line.updated`), een onderwerp (soort en id) met de zaak waar het bij hoort (opdracht of vacature) en de persoon over wie het gaat, een actor (persoon, gast, andere instantie, of het systeem met de naam van de taak), een herkomst (eigen of ontvangen van welke instantie), een correlatie-id dat alles verbindt wat één verzoek of één inkomend bericht veroorzaakte, de wijziging (oude en nieuwe waarden) en een toelichting. Elk veld van de wijziging draagt zijn gegevensklasse uit het toegangsmodel. De gebeurtenis zelf draagt de klasse die bepaalt wie mag weten dat ze plaatsvond.

**Eén manier van schrijven.** `grip.events.stream` schrijft een gebeurtenis in de transactie van de wijziging die ze beschrijft. Wordt de wijziging teruggedraaid, dan is de gebeurtenis er ook niet. De helper van de auditlog en `emit` blijven bestaan als dunne lagen eroverheen.

**Twee soorten afhandelaars.** Een transactionele afhandelaar loopt in de transactie van de gebeurtenis. Wat hij schrijft (een bericht in de uitbak, een teken dat de taken opnieuw bekeken moeten worden) vervalt samen met de wijziging, en als hij weigert, gaat de wijziging niet door. Hij raakt niets buiten de database. Een afhandelaar na vastlegging loopt pas als de transactie duurzaam is, en nooit voor een transactie die is teruggedraaid. Dat is de plek voor alles met een gevolg buiten de database.

**Volgorde.** Het volgnummer wordt uitgegeven onder een slot op de kop van de stroom, dat blijft staan tot de transactie eindigt. De volgorde van de stroom is daardoor de volgorde waarin transacties vastliggen. Een lezer met een cursor mist niets.

**Volledigheid als eigenschap.** Een test volgt elk verzoek en faalt als een tabel met domeingegevens is gewijzigd zonder gebeurtenis die dat dekt. Tabellen zonder domeingegevens staan op een lijst, elk met de reden.

**Aantoonbaar ongewijzigd.** Elke gebeurtenis draagt de hash van de vorige. De hash gaat over een canonieke vorm (RFC 8785) van de vaste gegevens en over gezouten afdrukken van de waarden. Een opdracht controleert de keten en zegt waar ze breekt. De database weigert het wijzigen en verwijderen van een gebeurtenis.

**Wissen zonder de keten te breken.** Een gebeurtenis verdwijnt nooit. Wat kan vervallen zijn haar waarden, samen met het zout van hun afdrukken. De afdrukken blijven, dus de keten blijft controleerbaar, en zonder zout is een afdruk van een kleine waarde niet terug te raden. Elke wisactie is zelf een gebeurtenis. De bewaartermijn is een instelling van de instantie.

**Twee manieren van lezen.** Mensen lezen de stroom als geschiedenis: per zaak, per persoon (wat iemand deed, en wat er met iemands gegevens is gedaan) en voor de hele instantie. Elke gebeurtenis wordt apart beoordeeld door het toegangsmodel, per veld. Wie wel mag weten dat iets veranderde en niet wat, ziet alleen dat. Er is geen totaal, en wat verborgen blijft laat geen spoor achter. Systemen lezen de stroom als een feed met een cursor, in het NL GOV-profiel voor CloudEvents, in het Nederlands en zonder waarden. De feed staat dicht tot de instantie er een sleutel voor instelt.

**Inzage wordt vastgelegd.** Geeft grip een veld van de klassen D, E of F terug, dan staat in de stroom wie dat las, wanneer, van wie en via welk verzoek.

## Gevolgen

- De tabel `audit_log` is vervangen door `stream_event`. Bestaande regels zijn in volgorde overgenomen als begin van de keten. Code die de auditlog leest, werkt ongewijzigd: `AuditLog` is nu de wijzigingsregels van de stroom.
- Schrijvende transacties wachten op elkaar vanaf het moment dat ze hun eerste gebeurtenis wegschrijven. Voor het gebruik van grip is dat geen probleem. Bij veel gelijktijdige schrijvers is het de eerste plek om naar te kijken.
- Een nieuw soort onderwerp moet een gegevensklasse krijgen in `grip.events.classification`. Zonder is het alleen voor de beheerder zichtbaar, en een test faalt.
- De persoon in een gebeurtenis is een id zonder verwijzing naar de persoonstabel: het record is gehasht en verandert niet als een persoon wordt verwijderd.
- De feed geeft bewust weinig. Een systeem dat meer wil weten, vraagt het ding zelf op en valt dan onder het toegangsmodel.
- Niet gebouwd: abonnementen met aflevering, het doorsturen naar een logboek volgens Logboek Dataverwerkingen, en het verankeren van de keten buiten de instantie. Zie `docs/gebeurtenissen.md`.

## Later gewijzigd (2026-10-09)

Inzage wordt sindsdien per verzoek vastgelegd, niet per persoon: een pagina over een persoon geeft een gebeurtenis over die persoon, een lijst geeft een gebeurtenis met de klassen en het aantal personen. Het overzicht voor mensen toont standaard alleen wijzigingen. Een selectie uit de stroom is het nieuws voor de lezer (ADR 0043).
