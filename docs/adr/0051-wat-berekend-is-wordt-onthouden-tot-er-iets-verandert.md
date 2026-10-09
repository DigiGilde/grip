# 0051 Wat berekend is wordt onthouden tot er iets verandert

Status: aanvaard

## Context

Afgeleide bedragen worden berekend en niet opgeslagen (ADR 0017). Op een database van ware grootte (400 opdrachten, 150 mensen, vier jaar) rekende elke lijst elke opdracht bij elk verzoek opnieuw door: de startpagina deed 12.000 queries en duurde 13 seconden, Factureren en Rapportage net zo.

## Besluit

De uitkomst van een leesmodel per opdracht blijft in het geheugen van het proces staan onder een sleutel die verandert zodra iets verandert waar de uitkomst op rust (`grip/services/read_cache.py`). Er wordt niets opgeslagen in de database en geen regel staat ergens anders dan in `grip/calc`.

De sleutel komt uit de gebeurtenissenstroom, die elke wijziging van domeingegevens vastlegt:

- de laatste gebeurtenis van de opdracht zelf;
- de laatste gebeurtenis die niet over precies één opdracht gaat (een tarievenkaart, een inzetschaal, een kostenpost, een persoon).

Alleen soorten gebeurtenissen die op de lijst `LOCAL_KINDS` staan gelden als "raakt alleen de eigen opdracht". Een nieuwe soort telt voor alle opdrachten tot iemand haar op de lijst zet. Het inzien van gegevens telt nooit.

Wat onthouden wordt is het volledige leesmodel in gewone waarden, zonder databaserijen. De route laat daarna weg wat de lezer niet mag zien, zoals altijd.

In de tests staat `READ_CACHE=verify`: elke onthouden waarde wordt opnieuw berekend en vergeleken, en een verschil laat de test falen.

De taakmotor volgt dezelfde gedachte: hij kijkt niet opnieuw naar alle zaken zolang de stroom en de dag niet veranderd zijn sinds dit proces dat voor het laatst deed.

## Gevolgen

- Een wijziging aan domeingegevens zonder gebeurtenis geeft een verouderd bedrag. De volledigheidstest (`grip.events.completeness`) bewaakt dat al; hij is nu ook voor de bedragen dragend.
- Een nieuw leesmodel dat onthouden wordt mag alleen rusten op gegevens met gebeurtenissen, en op de dag alleen als die in de sleutel zit.
- Na een wijziging die alle opdrachten raakt (een tarief, een kostenpost) rekent de eerste lezer alles opnieuw: enkele seconden op ware grootte. Dat staat in `docs/snelheid.md` als open punt.
- Elk proces heeft zijn eigen geheugen; na een herstart is het leeg.
- `READ_CACHE=off` zet het onthouden uit.
