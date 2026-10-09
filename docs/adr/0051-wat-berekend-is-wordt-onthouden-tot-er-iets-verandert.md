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

### Aanvulling: onthouden op inhoud

Een wijziging die niet over één opdracht gaat verandert de sleutel van alle opdrachten, terwijl ze de bedragen van weinig opdrachten verandert. Daarom is er een tweede geheugen, `read_cache.by_content`: de uitkomst van een zuivere berekening blijft staan onder een vingerafdruk van alles wat die berekening krijgt (de invoer voor `grip/calc`, de regels, de namen die ze toont, het jaar). Na zo'n wijziging wordt de invoer van alle opdrachten opnieuw gelezen, in een vast aantal queries, en wordt alleen gerekend voor de opdrachten waarvan de invoer anders is.

- Een berekening die zo onthouden wordt leest niets dan haar argumenten: geen database, geen klok.
- De vingerafdruk bevat alles wat de berekening krijgt. Van een databaserij tellen de kolommen die gelezen zijn.
- `READ_CACHE=verify` rekent ook hier elke onthouden waarde na.

De feiten van een opdracht voor de taakmotor worden op dezelfde manier onthouden als een leesmodel per opdracht. Daarbij tellen ook de gebeurtenissen over functies en vacatures mee, omdat de feiten daarop rusten (is er iemand die mag goedkeuren).

Het gedeelde stempel wordt per proces bijgehouden: een proces leest alleen de gebeurtenissen sinds het voor het laatst keek, en controleert daarbij dat de stroom nog dezelfde is (de hash van de gebeurtenis tot waar het keek). Alleen een sessie die zelf niets schreef legt vast tot waar gekeken is.

## Gevolgen

- Een wijziging aan domeingegevens zonder gebeurtenis geeft een verouderd bedrag. De volledigheidstest (`grip.events.completeness`) bewaakt dat al; hij is nu ook voor de bedragen dragend.
- Een nieuw leesmodel dat onthouden wordt mag alleen rusten op gegevens met gebeurtenissen, en op de dag alleen als die in de sleutel zit.
- Na een wijziging die alle opdrachten raakt (een tarief, een kostenpost) leest de eerste lezer alle invoer opnieuw en rekent alleen wat anders is: een halve tot een hele seconde op ware grootte. Na een herstart wordt alles één keer gerekend: een tot twee seconden per pagina. De cijfers staan in `docs/snelheid.md`.
- Het geheugen is begrensd op een aantal waarden (`READ_CACHE_MAX_ENTRIES`, standaard 8000); de oudste gaan eerst.
- Elk proces heeft zijn eigen geheugen; na een herstart is het leeg.
- `READ_CACHE=off` zet het onthouden uit.
