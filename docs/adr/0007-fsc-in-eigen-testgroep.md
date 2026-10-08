# 0007 FSC in een eigen testgroep, productie-FSC later

Status: aanvaard (2026-10-08)

## Context

Instanties bij verschillende organisaties moeten elkaar veilig kunnen aanroepen. FSC (Federated Service Connectivity) is daarvoor de standaard binnen de overheid: verkeer loopt via een outway en een inway met wederzijdse TLS, en een contract bepaalt welke dienst een deelnemer mag aanroepen.

Voor de eerste mijlpaal is productie-FSC met PKIoverheid-certificaten niet vereist. Het alternatief was direct HTTPS-verkeer, met FSC als latere stap.

## Besluit

Vanaf het begin loopt verkeer tussen instanties via FSC, in een eigen testgroep met een eigen CA en zelf uitgegeven certificaten. De overstap naar productie-FSC is daarna een wissel van groep en certificaten.

## Gevolgen

- Elke deelnemer draait een manager, inway, outway, controller en transactielog, met tot drie databases. De groep heeft een directory en een gedeelde CA nodig.
- De applicatie stuurt verzoeken naar de eigen outway met de header `Fsc-Grant-Hash` en leest het peer-id uit wat de inway doorgeeft. Inkomende federatieroutes mogen alleen via de inway bereikbaar zijn.
- Het hostingplatform moet TLS-afhandeling in de pod toestaan. Of dat op productie aanstaat is niet bevestigd.
- Het aantal componenten groeit met elke deelnemer, ook met elke extra Bouwmeester-instantie.
