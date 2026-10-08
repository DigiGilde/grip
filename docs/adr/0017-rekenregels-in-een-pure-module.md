# 0017 Rekenregels in een pure module

Status: aanvaard (2026-10-08)

## Context

In Grist staan de berekeningen als formules in kolommen. Bij een overstap naar een applicatie kunnen dezelfde regels op meerdere plaatsen terechtkomen: in een query, in een service, in de frontend. Dan lopen ze uit elkaar.

De eerste eis aan grip is dat het de totalen uit Grist tot op de euro reproduceert.

## Besluit

De rekenregels R1 t/m R14 staan in een module, `backend/grip/calc`. Die module gebruikt geen database, geen HTTP en geen klok. Niets anders implementeert een regel opnieuw.

- Geld is een geheel aantal centen.
- FTE en percentages zijn exacte decimalen.
- Afronden gebeurt pas bij het tonen of vastleggen van een totaal.
- Afgeleide waarden worden berekend en niet opgeslagen.
- Een uitgegeven offerte is de uitzondering: een bevroren momentopname.

## Gevolgen

- De module is te testen zonder database, met de rekenvoorbeelden en later met gevallen uit de echte export.
- Overzichten over veel opdrachten rekenen bij elk verzoek opnieuw. Wordt dat te traag, dan komt er een cache en geen opgeslagen kolom.
- De frontend toont bedragen die de backend heeft berekend en rekent zelf niet.
