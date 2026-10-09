# 0046 Eén klok: een datum is de dag van de instantie

Status: aanvaard (2026-10-09)

## Context

Grip kende twee manieren om te bepalen welke dag het is. Een deel van de code vroeg de lokale dag van het proces, een ander deel nam de dag in UTC. Tussen middernacht en één of twee uur 's nachts verschillen die: in UTC is het dan nog gisteren. Een recht dat kort na middernacht werd toegekend ging in op de lokale dag, terwijl het zoeken van een goedkeurder en het besluit met de dag in UTC rekenden. Het recht telde dus nog niet. Hetzelfde verschil zat in de factuurdatum, het maandoverzicht, de facturatieperioden, het jaar van een offertenummer en de datum op documenten. Een proces dat in een container op UTC draait, verschuift bovendien elke "lokale" dag.

## Besluit

Er is één klok, `grip.core.clock`, en één regel.

- Een moment (iets gebeurde op dit tijdstip) wordt opgeslagen in UTC.
- Een datum van het domein (een recht geldt vanaf een dag, een tarievenkaart eindigt op een dag, een maand is voorbij, een termijn verloopt) is een dag op de kalender van de organisatie. Dat is de datum in de tijdzone van de instantie, `INSTANCE_TIMEZONE`, standaard `Europe/Amsterdam`.

`clock.today()` geeft die dag, `clock.now()` het moment in UTC en `clock.local_date(moment)` de dag waarop een opgeslagen moment viel. Code vraagt de dag nergens anders: geen `date.today()`, geen `datetime.now(UTC).date()` en geen `.date()` op een opgeslagen moment. De schermen gebruiken dezelfde regel via `todayIso` in `frontend/src/lib/today.ts`.

## Gevolgen

- Toekennen en beslissen rekenen met dezelfde dag. Een recht van vandaag telt vandaag, ook om half één 's nachts.
- De datum op een offerte, een factuurverzoek en een rapport is de dag in Nederland waarop het gebeurde, niet de dag in UTC.
- De tijdzone van het proces of van de container doet er niet meer toe.
- Een test zet het moment met `clock.at(...)`. De tests in `backend/tests/test_clock.py` spelen hetzelfde scenario af om 23:30 en om 00:30 op een maandgrens, een jaargrens en rond beide wisselingen van zomer- en wintertijd.
- De rekenmodule blijft zonder klok: wie haar aanroept, geeft de dag mee.
- Een kolom met een standaardwaarde in de database (`current_date`) volgt de tijdzone van de databasesessie. Code die een rij maakt, geeft de dag daarom zelf mee.
