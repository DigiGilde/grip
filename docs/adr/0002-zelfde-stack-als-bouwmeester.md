# 0002 Zelfde stack als Bouwmeester

Status: aanvaard (2026-10-08)

## Context

De basisbeschrijving van het Grist-document stelde Node.js met TypeScript voor. Die keuze kwam voort uit de vraag of "node based" Node.js betekende. Bedoeld was: gebaseerd op de nodes van het corpus.

Bouwmeester draait op FastAPI, SQLAlchemy 2 async, Postgres en Alembic, met `uv` en `just`, en een frontend in React met Vite en `@nldd/design-system`. Het heeft werkende patronen voor OIDC via SSO Rijk, sessies, functies per eenheid en een test die routes zonder autorisatie afkeurt.

## Besluit

Grip gebruikt dezelfde stack als Bouwmeester. Het domein, de rekenregels en de acceptatiecriteria uit de basisbeschrijving nemen we over; de stackkeuze niet.

## Gevolgen

- Code voor login, sessies en autorisatie is over te nemen.
- Wie aan het ene systeem werkt, vindt de weg in het andere.
- De rekenmodule wordt in Python geschreven. Exacte decimalen en hele centen moeten daar bewust worden afgedwongen.
