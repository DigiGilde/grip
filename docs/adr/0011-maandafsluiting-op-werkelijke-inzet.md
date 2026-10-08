# 0011 Maandafsluiting op werkelijke inzet

Status: aanvaard (2026-10-08)

## Context

In Grist is inzet een FTE-percentage over een periode, en het inzetbedrag volgt uit percentage maal maandtarief. Er worden geen uren geschreven. Verrekening met de opdrachtgever moet wel kloppen met wat er werkelijk is gedaan.

Urenregistratie zou dat oplossen, maar hoort niet bij de eerste mijlpaal.

## Besluit

Verrekening gaat per maand op werkelijke inzet. De geplande inzet staat klaar als voorstel. De manager van de opdracht past afwijkingen aan en sluit de maand af. De vastgestelde inzet voedt de uitputting en de factuurgegevens.

## Gevolgen

- Er komt een entiteit `month_close` met de vastgestelde inzet per persoon per maand.
- Een afgesloten maand is vergrendeld. Wie hem mag heropenen is niet beslist.
- De rekenregels R9 en R12 moeten beschrijven hoe vastgestelde en geplande inzet samen optellen. Dat is nog niet gedaan.
- De prijs van een gedeeltelijke maand en een door de manager vastgesteld percentage kunnen elkaar overlappen. Dat moet bij het uitwerken van de afsluiting worden opgelost.
