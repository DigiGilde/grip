# 0060 Het contract staat in grip, tot een tweede systeem het implementeert

Status: aanvaard (2026-11-28)

## Context

[ADR 0006](0006-contract-eerst-in-neutrale-repo.md) zette de contracten `grip-opdrachtverkeer` en `corpus-context` in een eigen repo, omdat meer dan een systeem ze zou implementeren. Grip droeg een kopie mee, vastgepind op een commit en ververst met `just sync-contract`.

Grip is nog de enige implementatie. Het speelt beide kanten: het verkeer tussen grip-instanties, en met de stand-in onder `backend/grip/dev/corpus_standin/` ook het corpus. Bouwmeester implementeert `corpus-context` niet op `main`. De eigen repo had geen eigenaar en geen wijzigingsproces. Elke wijziging kostte twee pull requests en een sync, en het contract stond op twee plekken.

## Besluit

Het contract staat in grip, in `backend/grip/federation/contract/`, met zijn geschiedenis. Dat is de enige plek. De eigen repo vervalt.

- De map houdt alles wat de eigen repo had: OpenAPI, schema's, woordenlijst, JSON-LD-context, voorbeelden, de regels van de API Design Rules en de scripts. `just contract-check` en de CI-job `contract` lint, valideren en bouwen de leespagina's.
- De versie van een dienst is `info.version` in zijn OpenAPI-document. Er is geen vastgepinde commit meer.
- De rest van ADR 0006 blijft: contract eerst, semver met `/v1` in het pad, de woordenlijst als voorstel, het contract geserveerd op `/v1/openapi.json`.

## Gevolgen

- Een wijziging in een koppelvlak begint nog steeds in het contract, nu in dezelfde pull request als de code die het volgt.
- Een ander systeem dat het contract implementeert, neemt de map over op een commit van grip.
- Zodra een tweede systeem het contract echt implementeert, krijgt het weer een eigen repo met een eigenaar. De map staat los van de code en is met haar geschiedenis af te splitsen.
