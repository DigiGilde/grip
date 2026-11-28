# 0053 Een gegeven heeft één eigenaar, elders een verwijzing

Status: voorgesteld (2026-10-10)

## Context

Grips werken samen: een programma meldt kosten bij een leverancier, een opdrachtgever volgt acties bij een opdrachtnemer. De eerste opzet van ADR 0052 bewaarde bij de opdrachtgever een kopie van de factuurregels van de leverancier, alleen te lezen en met herkomst. Een kopie kan verouderen, kan bij wijzigingen en wissen achterblijven, en maakt onduidelijk welke Grip de waarheid heeft. Dezelfde vraag komt terug bij acties uit een overleg en bij alles wat later tussen Grips gaat.

## Besluit

**Elk gegeven heeft precies één eigenaar-Grip.** Alleen daar ontstaat het, alleen daar wijzigt het en alleen daar wordt het gewist. Wie een gegeven bij een ander laat ontstaan, vraagt de eigenaar via FSC om het aan te maken.

**Elders staat een verwijzing.** Een andere Grip bewaart de URI van het gegeven en wat van haarzelf is: hoe zij het dekt, bij welke dienst het hoort, eigen labels. Dat is aanvulling, geen kopie. Velden van de eigenaar staan niet in de verwijzing.

**Lezen is federatief.** De verwijzende Grip haalt de inhoud bij de eigenaar op. De eigenaar beslist met `decide()` wat de ander mag zien. Rapporten halen per eigenaar in één verzoek op, niet per gegeven.

**De eigenaar kent wie verwijst.** Een gegeven dat op verzoek ontstaat, draagt wie het vroeg en de URI van de verwijzing. Daaruit volgt wie mag lezen. Meldingen bij wijziging en abonnementen voor meer luisteraars komen pas als lezen op het moment zelf niet volstaat.

**Berekenen blijft puur.** De servicelaag haalt de inhoud op en geeft die aan `grip.calc`. Wat is opgehaald, wordt hooguit kort onthouden; dat is een geheugensteun, geen bron.

**Onbereikbaar is onbekend.** Kan de eigenaar niet worden bereikt, dan toont de verwijzende Grip geen getal maar "niet op te halen", en heet een totaal waar het in hoort onvolledig. Een oude stand doet zich nooit voor als de huidige.

**Een verzoek om aan te maken mag wachten.** Is de eigenaar onbereikbaar, dan blijft het verzoek in de outbox staan en toont de verwijzing "wacht op" de eigenaar. Het gegeven bestaat pas als de eigenaar het heeft aangemaakt.

**Vastleggen is iets anders dan kopiëren.** Wat op een moment moet blijven staan, zoals een verantwoording aan een opdrachtgever, wordt een vastgelegd document met de stand van dat moment, zoals een offerte. Dat document wordt niet bijgewerkt en is geen werkkopie.

## Gevolgen

- ADR 0052 volgt dit besluit: een kostenpost bij een andere partij is een verwijzing.
- Acties uit een overleg (nog te besluiten) leven bij de Grip waar ze zijn toegewezen; een opdrachtgever volgt ze via een verwijzing.
- Een uitgegeven offerte blijft een bevroren momentopname. Dat is vastleggen, geen kopie.
- Elke nieuwe soort verwijzing vraagt een operatie om aan te maken, een operatie om op te halen en een regel in `decide()` bij de eigenaar.
- Federatie wordt een voorwaarde voor een volledig beeld. Zonder bereikbare eigenaar is een uitputting onvolledig, en het scherm zegt dat.
