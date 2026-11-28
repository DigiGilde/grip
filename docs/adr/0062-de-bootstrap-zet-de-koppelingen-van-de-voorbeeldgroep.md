# 0062 De bootstrap zet de koppelingen van de voorbeeldgroep

Status: voorgesteld (2026-11-28)

## Context

De voorbeeldgroep op ZAD gaat van twee naar zeven instanties: GDI voorbeeld, Ministerie van BZK voorbeeld, MOZa voorbeeld, ODI voorbeeld, DigiGilde voorbeeld, Ministerie van EZK voorbeeld en NLDD voorbeeld. Tussen de instanties die met elkaar te maken hebben, staan zeven relaties, elk aan beide kanten in het peerregister: veertien rijen, met per rij de grant hash uit een verbindingscontract en de rol van de ander (tegenpartij, moeder of dochter).

Tot nu toe printte de bootstrap van elke peer (`deploy/zad/fsc/bootstrap.sh`) die rijen in zijn log, en voerde een beheerder ze met de hand in onder Beheer, Koppelingen. Bij twee instanties ging dat al traag: wie het register vult, moet bij elke instantie kunnen inloggen. Lokaal schreef `deploy/local/fsc-bootstrap.sh` de rijen rechtstreeks in de database, buiten de regels van grip om. Het ontwerp van de voorbeeldketen vraagt dat de bootstrap de koppelingen meteen zet, via grip, zonder de rechten van grip te omzeilen. Sinds ADR 0061 maakt de volgorde niet meer uit: een bericht naar een peer die de afzender nog niet kent, blijft het proberen.

## Besluit

**Een route voor de bootstrap.** Grip krijgt twee routes voor een systeem met een sleutel, zoals de export naar Wies (ADR 0013) en de stroom van gebeurtenissen:

- `PUT /api/peers/registry` legt een andere voorbeeldinstantie vast of brengt haar rij in lijn met het contract: peer-id, naam, TOOI-URI, basis-URI, rol en grant hash.
- `POST /api/peers/registry/test-connection` doet voor die peer wat "Test de verbinding" doet, en geeft de uitkomst terug.

De bootstrap biedt de sleutel `PEER_REGISTRY_KEY` aan als bearer-token. Zonder ingestelde sleutel staan de routes dicht. Een sessie telt niet; daarom vragen ze geen CSRF-token.

**De beslisfunctie beslist.** De sleutel zegt wie er vraagt: de machine `fsc-bootstrap`, een nieuw soort subject naast persoon, gast en peer. Of die het mag, beslist `decide` met de nieuwe handeling `register_peer` op de instantie. Die staat het alleen toe waar voorbeeldgegevens mogen bestaan: een voorbeeldinstantie, of een lokale ontwikkelinstantie zonder login. Een instantie voor echt werk weigert, ook met de juiste sleutel. Een persoon, ook de beheerder, gebruikt deze handeling niet; die beheert het register zoals voorheen.

**Wat de bootstrap zet, en wat niet.** Een nieuwe rij krijgt alles, ook financiële inzage als de relatie die vraagt (NLDD bij DigiGilde). Op een bestaande rij voegt de bootstrap de grant hash toe en zet hij naam, TOOI-URI, basis-URI en rol. Of een peer actief is en financiële inzage heeft, is van de beheerder: de bootstrap raakt dat niet meer aan, ook niet bij zijn controle elk uur. Een rij is een voorbeeld als de instantie een voorbeeld is. Elke wijziging komt in het auditlog met de bron `fsc-bootstrap`. Een aanroep die niets verandert, schrijft niets.

**De relaties.** Welke peers met elkaar verbonden zijn en met welke rol, staat in een tabel in de bootstrap, lokaal en op ZAD gelijk. Een verbindingscontract is er alleen tussen peers die een relatie hebben, in beide richtingen.

## Gevolgen

- Na een uitrol staan de koppelingen er zonder handwerk, en de bootstrap meldt per koppeling of "Test de verbinding" in orde is. Dat is te lezen in het log van `fscboot-<k>`, zonder in te loggen.
- Elke uitrol met FSC krijgt een geheim erbij: `PEER_REGISTRY_KEY`, gelijk op `component-2` en op `fscboot-<k>`. Zonder dat geheim print de bootstrap de rijen zoals voorheen.
- Wie de sleutel heeft, kan in een voorbeeldinstantie een peer van de voorbeeldgroep vastleggen. Een voorbeeld praat alleen met voorbeelden (ADR 0054), en de sleutel staat alleen in de eigen uitrol.
- Dit is een oplossing voor de voorbeeldgroep. Een instantie voor echt werk vult haar register niet zo; daar doet een beheerder het, hooguit geholpen door een tijdelijke sleutel voor de eerste inrichting (de eigenaar van grip, 28 november 2026).
- Een corpus-systeem is geen instantie: de lokale Bouwmeester blijft een eigen weg houden (`fsc-bootstrap-corpus.sh`).
- `grip.dev.seed` en de route lezen dezelfde voorwaarde voor voorbeeldgegevens (`Settings.may_hold_example_data`).
