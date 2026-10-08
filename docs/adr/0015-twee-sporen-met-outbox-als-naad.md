# 0015 Twee sporen met de outbox als naad

Status: aanvaard (2026-10-08)

## Context

Grip heeft twee soorten werk. Het ene vervangt Grist: begroting, inzet, kosten, offerte, verrekening. Het andere bouwt het verkeer tussen instanties via FSC. Het eerste levert snel iets bruikbaars; het tweede heeft afhankelijkheden buiten het team, zoals het hostingplatform.

Na elkaar bouwen houdt Grist langer in gebruik of stelt de risico's van FSC uit.

## Besluit

De sporen lopen tegelijk. Spoor A vervangt Grist, spoor B bouwt de federatie.

- Spoor A levert een servicelaag en schrijft elke relevante gebeurtenis naar de tabel `federation_outbox`.
- Spoor B verstuurt uit de outbox en verwerkt inkomende berichten via de servicelaag van spoor A.
- Spoor B raakt geen domeintabellen rechtstreeks. Spoor A weet niets van FSC.

## Gevolgen

- Een opdracht werkt volledig zonder spoor B. Interne opdrachten en tegenpartijen zonder grip hebben het verkeer niet nodig.
- Is een tegenpartij onbereikbaar, dan blijven berichten in de outbox staan en werkt de applicatie door.
- Welke gebeurtenissen "relevant" zijn moet tussen de sporen worden afgesproken en ligt vast in het contract.
- De servicelaag is een intern koppelvlak. Wijzigingen daarin raken beide sporen.
