# 0012 Factuurgegevens, geen facturen

Status: aanvaard (2026-10-08)

Aangevuld door: [0023 Aangeleverd is niet gefactureerd](0023-aangeleverd-is-niet-gefactureerd.md)

## Context

Opdrachten worden verrekend met de opdrachtgever. Binnen het Rijk is dat vaak een interne verrekening, daarbuiten een factuur. De organisatie heeft een financieel systeem waar die ontstaan.

In Grist betekent "Factuur" iets anders: een regel aan de inkoopkant, op een kostenpost.

## Besluit

Grip levert per periode factuurgegevens voor het financiële systeem. Het maakt zelf geen factuur, verstuurt er geen en volgt geen betaling.

De term "factuur" blijft in grip gereserveerd voor de inkoopregel op een kostenpost. ADR 0023 voegt daar de uitgaande factuur aan toe: de vastlegging dat een factuur is verstuurd.

## Gevolgen

- Er is een export nodig. Het doelsysteem en het formaat zijn niet bekend.
- Een opdrachtgever kan de factuurgegevens van een opdracht op verzoek ophalen via het opdrachtverkeer.
- E-factureren volgens NLCIUS valt buiten grip.
