# 0006 Contract eerst, in een neutrale repo

Status: aanvaard (2026-10-08)

## Context

Twee koppelvlakken worden door meer dan een systeem geïmplementeerd: `grip-opdrachtverkeer` door elke grip-instantie, `corpus-context` door elke Bouwmeester en later mogelijk andere corpus-systemen. Instanties draaien niet allemaal dezelfde versie.

FastAPI genereert een beschrijving van de API uit de code. Die verandert zodra iemand een model aanpast. Bouwmeester zet die beschrijving in productie uit.

Node-typen zijn in Bouwmeester een vrije tekst en edge-typen een register waar gebruikers eigen typen aan toevoegen.

## Besluit

De contracten staan in een eigen repo, los van grip en van Bouwmeester.

- Een OpenAPI 3.1-document per dienst, met JSON Schema-bestanden (2020-12) voor de objecten.
- Versies met semver en `/v1` in het pad, gecontroleerd met de Spectral-regels van de API Design Rules.
- Een woordenlijst met een vaste kern van node-typen en edge-typen, elk met een URI. Eigen typen mogen in een eigen naamruimte.
- Een JSON-LD-context, zodat de schema's als linked data leesbaar zijn.
- Elke implementatie serveert het contract op `/v1/openapi.json` en bewijst met contracttests in CI dat ze voldoet.

De documentatiepagina van FastAPI blijft als weergave. Ze is niet het contract.

## Gevolgen

- Een wijziging in een koppelvlak begint in de contractrepo en niet in de code.
- De gedeelde kern van typen moet met de beheerders van het corpus worden vastgesteld. Tot dan is de woordenlijst een voorstel.
- De contractrepo heeft een eigenaar en een wijzigingsproces nodig. Die zijn nog niet aangewezen.
- RDF en SHACL blijven buiten de eerste mijlpaal.
