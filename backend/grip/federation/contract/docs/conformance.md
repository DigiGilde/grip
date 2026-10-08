# Voldoen aan het contract

Een implementatie voldoet als ze de drie controles hieronder in haar eigen CI draait en ze slagen.
Leg de versie van het contract vast (een tag van deze repo), zodat een wijziging hier een bewuste
stap is in de implementatie.

## 1. De gegenereerde OpenAPI vergelijken met het contract

De meeste implementaties genereren hun OpenAPI uit code. Die beschrijving is een weergave, geen
contract. Vergelijk haar met het contract:

```
just docs
just compare corpus-context pad/naar/openapi.json /api/federatie/v1
```

Het derde argument is het voorvoegsel dat de implementatie voor deze routes gebruikt; laat het weg
als de paden gelijk zijn. De vergelijking faalt als een operatie, een query-parameter of een
succesantwoord uit het contract ontbreekt. Extra operaties in de implementatie zijn toegestaan.

## 2. Antwoorden en berichten valideren tegen de schema's

De vergelijking hierboven kijkt niet naar de inhoud. Valideer daarom in de tests van de
implementatie elk antwoord van een contractroute tegen het bijbehorende schema uit `schemas/`, en
elk bericht dat de implementatie verstuurt voordat het de outbox ingaat. Gebruik een validator
voor JSON Schema 2020-12 met controle op `format`.

Neem ook de voorbeelden mee: elk bestand in `examples/valid/` moet door de implementatie worden
geaccepteerd, en de berichten in `examples/invalid/` moeten met 400 worden geweigerd.

## 3. De regels die een schema niet kan uitdrukken

Test deze expliciet:

| Regel | Verwacht gedrag |
|---|---|
| Idempotentie | Hetzelfde `id` met dezelfde inhoud geeft 200 met `outcome` `duplicate` en geen tweede verwerking; met andere inhoud 409 |
| Offertehash | `snapshot_hash` is de SHA-256 over de canonieke JSON (RFC 8785) van `snapshot`; een verschil geeft 400 |
| Akkoord | `quote_hash` hoort bij de uitgegeven offerte, anders 409; de JWS verifieert met een sleutel uit de JWKS van de afzender en de payload is gelijk aan de velden van het bericht |
| Relatie | Een peer zonder de relatie uit `x-grip-caller` krijgt 403 of 404, nooit gegevens |
| Gegevensklasse | Een antwoord bevat geen velden uit een andere klasse dan `x-grip-data-class` noemt; namen van medewerkers alleen in `GET /handover/staffing` |
| Inzage op verzoek | Operaties met `x-grip-on-request` geven 403 zolang de opdrachtnemer ze niet heeft toegestaan |
| Peildatum | Een node opgevraagd met een `peildatum` in het verleden geeft de titel en status van die datum |
| Ander corpus | Een node-URI uit een ander corpus wordt geaccepteerd waar een node-URI staat, en niet zelf opgelost |
| Versie | Elk succesantwoord draagt `API-Version`; de implementatie serveert het contract op `/v1/openapi.json` |
| Bereikbaarheid | De federatieroutes zijn alleen via de inway bereikbaar; een verzoek dat de peer-header zelf zet en niet via de inway komt, wordt niet bediend |

`scripts/validate.mjs` in deze repo laat zien hoe de offertehash en de JWS van het akkoord worden
nagerekend.
