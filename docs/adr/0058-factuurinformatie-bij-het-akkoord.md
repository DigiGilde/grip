# 0058 Factuurinformatie wordt bij het akkoord opgegeven

Status: voorgesteld (2026-11-25)

## Context

Bij het aanleveren van een factuurperiode vroeg grip de opdrachtnemer om het factuuradres van de opdrachtgever. Volgens [ADR 0039](0039-afsluiten-per-maand-aanleveren-per-periode.md) vult de opdrachtgever de bijlage Factuurinformatie van de offerte in en neemt de opdrachtmanager die één keer over bij de factuurafspraken. Wie de offerte in grip tekent, levert die bijlage niet in; het adres moest dan later worden nagevraagd. De pdf van een offerte is een exportmiddel en niet de gewone weg.

## Besluit

1. **De opdrachtgever geeft de factuurinformatie bij het akkoord.** In alle drie de vormen van tekenen ([ADR 0010](0010-tekenen-in-drie-vormen.md)) staan de velden van de bijlage: organisatie, ten name van, adres of postbus, postcode en plaats, een kenmerk voor op de factuur en een contactpersoon van de financiële afdeling. Ze komen bij de opdrachtnemer in de factuurafspraken van de opdracht.
2. **Verplicht als de offerte de bijlage heeft.** Organisatie, adres en postcode met plaats zijn dan verplicht bij tekenen met een tekenlink en in de eigen grip. Het kenmerk is optioneel en wordt vooraf gevuld met "Uw kenmerk" uit de offerte. Bij een getekende pdf neemt de medewerker over wat er is ingevuld; daar is niets verplicht.
3. **Wat de opdrachtgever opgeeft wint.** Het vervangt wat de opdrachtmanager eerder invulde. Een factuurverzoek dat al is aangeleverd blijft zoals het was.
4. **Een opdrachtgever met een eigen grip wijzigt het adres later zelf.** Die grip bewaart wat hij opgaf (de opdrachtgever is eigenaar, [ADR 0053](0053-een-gegeven-heeft-een-eigenaar-elders-een-verwijzing.md)) en stuurt een wijziging met `sendBillingDetails`. De opdrachtnemer neemt een wijziging alleen over als die later is opgegeven dan wat hij heeft; een moment in de toekomst telt als nu.
5. **Contract 1.2.0.** Het akkoord krijgt het optionele veld `factuurinformatie`, buiten de JWS; `sendAcceptance` draagt daarmee gegevensklasse A en B. `PUT /opdrachten/{opdrachtId}/factuurinformatie` is nieuw.
6. **Niet in het bewijs.** De factuurinformatie staat niet in de akkoordverklaring en niet onder de handtekening ([ADR 0029](0029-bewijs-van-een-akkoord.md)). Het bewijs gaat over het besluit op de offerte; een factuuradres verandert.

## Gevolgen

- Vervangt het laatste gevolg van ADR 0039: de opdrachtmanager hoeft de bijlage niet meer over te nemen als er in grip is getekend. Het aanleveren vraagt alleen nog om het adres als het ontbreekt.
- Een opdrachtgever zonder eigen grip, die alleen met een tekenlink tekent, kan na het akkoord niets meer wijzigen. Voor die opdrachtgever past de opdrachtmanager het adres met de hand aan in Factuurafspraken.
- Nieuwe actie in de beslisfunctie: factuurinformatie opgeven. Een gast met een tekenlink mag dat alleen bij de offerte waarvoor hij is uitgenodigd, en krijgt er geen recht tot wijzigen bij.
- Naam, telefoon en e-mail van de contactpersoon zijn persoonsgegevens in klasse B.
- Migratie `0045_billing_details_given`: het moment van opgeven in de factuurafspraken, en een tabel met wat deze instantie als opdrachtgever opgaf.
- De oudere directe routes voor een akkoord zonder login nemen geen factuurinformatie aan.

## Wat niet is uitgezocht

- Een nieuwe link per mail, zodat ook een gast het adres later zelf kan wijzigen.
- Een bewaartermijn voor de contactpersoon.
- Of de factuurinformatie in de kroniek hoort als opgegeven feit, met wie en wanneer.
- Een handtekening van een tekenbevoegde in de pdf, als die er toch om vraagt (issue #24).
