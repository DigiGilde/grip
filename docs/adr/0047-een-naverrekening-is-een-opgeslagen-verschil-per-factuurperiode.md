# 0047 Een naverrekening is een opgeslagen verschil per factuurperiode

Status: aanvaard (2026-10-09)

## Context

Verandert de prijs van een maand die al is aangeleverd (een inzetschaal of een tarievenkaart met terugwerkende kracht), dan is het verschil nog aan te leveren: een naverrekening. Grip rekende dat verschil elke keer opnieuw uit op het scherm waar het getoond werd. De taken en het verloop van een opdracht konden het daardoor niet weten: elke maand opnieuw prijzen bij elke evaluatie is te duur. Het gevolg was een plicht zonder taak.

## Besluit

Het verschil wordt een rij (`billing_correction`) per opdracht en factuurperiode, geschreven in dezelfde transactie als de wijziging die het veroorzaakt.

- De rij bevat het bedrag, het bedrag per maand, de oorzaak in woorden, de aanlevering waar zij op volgt, wanneer en door wiens handeling zij ontstond.
- Per periode is er hooguit een open rij. Een tweede wijziging voor de aanlevering telt erbij op, met haar eigen oorzaak. Is het verschil weer nul, dan verdwijnt de rij.
- Een aanlevering die het verschil meeneemt sluit de rij en verwijst ernaar.
- De taak, het verloop van de periode, de rij op "Afsluiten en factureren" en de pagina Factureren lezen de rij. Niets rekent het verschil nog uit om het te tonen.
- Een maand die na aanlevering wordt heropend is geen naverrekening. Zij wordt in haar geheel opnieuw aangeleverd en het nieuwe verzoek vervangt het oude; een open verschil op die maand vervalt bij het heropenen.

## Gevolgen

- Wie een prijs wijzigt buiten `grip.services.rates` om, moet `billing_corrections.sync` aanroepen in dezelfde transactie. Zonder die aanroep toont grip het verschil niet meer.
- De gebeurtenis `billing_correction.arose` wordt een keer per ontstane of gewijzigde naverrekening uitgegeven, met de periode, in plaats van per maand.
- Bestaande verschillen van voor deze wijziging hebben geen rij en zijn daarmee uit beeld. Draai na migratie `0036_billing_correction` een keer `just billing-corrections-sync`: dat legt ze vast.
