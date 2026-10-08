# 0014 De salarisschaal wordt niet opgeslagen

Status: aanvaard (2026-10-08)

## Context

In Grist staat de schaal van een persoon in vrije tekst, soms met twee waarden: de werkelijke salarisschaal en de schaal waartegen wordt gedeclareerd. De basisbeschrijving nam beide op als veld en vroeg zich af of de salarisschaal nodig is.

Alle rekenregels gebruiken de inzetschaal. De salarisschaal is een persoonsgegeven zonder doel in grip.

## Besluit

Grip slaat alleen de inzetschaal op (`billing_scale`), met een geldigheidsperiode. De salarisschaal wordt niet opgeslagen en bij de import niet overgenomen.

## Gevolgen

- De import leest de vrije tekst uit Grist, haalt er de inzetschaal uit en laat de rest liggen. Een mens bevestigt de omzetting.
- Waar de inzetschaal gelijk is aan de salarisschaal, staat die schaal feitelijk toch in grip. De afscherming van klasse D blijft daarom nodig.
- Wie later een doel voor de salarisschaal heeft, schrijft een nieuwe ADR.
