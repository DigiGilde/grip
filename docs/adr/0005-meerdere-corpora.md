# 0005 Meerdere corpora, node-URI's per corpus

Status: aanvaard (2026-10-08)

## Context

Er komen meerdere Bouwmeester-instanties, bijvoorbeeld een per departement. Bouwmeester geeft een node nu alleen een UUID. Er is geen stabiele URI, en het adres van de API is een hostnaam van het hostingplatform.

## Besluit

De instantie die een node beheert geeft de URI uit: `{corpus-basis}/id/node/{uuid}`. De basis is een duurzaam domein per corpus.

Elke Bouwmeester publiceert dezelfde FSC-dienst, `corpus-context` v1. Grip houdt een register bij van corpus-basis naar peer en contract, gevuld vanuit de FSC-directory, en kiest de peer aan de hand van de URI.

Een opdracht mag naar nodes uit meerdere corpora verwijzen.

## Gevolgen

- Grip heeft geen instelling voor een vaste Bouwmeester.
- Per corpus is een vast domein nodig dat een verhuizing van hosting overleeft. Wie die domeinen beheert is niet belegd.
- Elke Bouwmeester-instantie is een eigen FSC-deelnemer met eigen componenten.
- Verwijzingen tussen corpora onderling regelt grip niet. Het contract laat node-URI's uit een ander corpus wel toe.
