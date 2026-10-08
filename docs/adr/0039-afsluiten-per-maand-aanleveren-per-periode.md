# 0039 Afsluiten per maand, aanleveren per factuurperiode

Status: aanvaard (2026-10-08)

## Context

Het tabblad Maandafsluiting deed alles per maand: een maand afsluiten, de factuurgegevens van die maand als csv-bestand exporteren, en voor die maand vastleggen dat er een factuur was verstuurd. Dat botst op drie plekken met hoe het werk gaat.

De offertes van de organisatie factureren per kwartaal of per maand. Het ritme is een afspraak met de opdrachtgever en verschilt per opdracht. Een opdrachtmanager die per kwartaal factureert, leverde drie keer iets aan en legde drie keer dezelfde factuur vast.

Een csv-bestand is bedoeld voor een systeem. Wie het ontvangt is een mens bij de financiële administratie, die er een factuur van moet maken. Die heeft nodig: aan wie de factuur gaat en welk kenmerk erop moet, over welke afspraak en periode het gaat, de regels en het totaal. Welk formaat een financieel systeem zou willen, is nooit vastgesteld.

"Aangeleverd" werd een maand op het moment dat iemand op exporteren klikte. Aan wie er iets was geleverd, en of het was aangekomen, stond nergens.

## Besluit

**Twee handelingen, elk met een eigen ritme.** Vaststellen wat er is gewerkt gebeurt per maand, kort na de maand: het is boekhouding van wat er is gebeurd, en het geheugen vervaagt. Factureren volgt de afspraak: per maand of per kalenderkwartaal. Een factuurperiode kan worden aangeleverd zodra al haar maanden zijn afgesloten.

**Het ritme hoort bij de opdracht.** De opdracht heeft factuurafspraken: het ritme, wat de opdrachtgever voor de factuur heeft opgegeven (organisatie, ten name van, adres, postcode en plaats, een kenmerk, de contactpersoon van de financiële afdeling) en of de specificatie mensen bij naam noemt. Zonder eigen afspraak volgt de opdracht de instelling van de instantie (`billing.rhythm`, standaard per kwartaal). De zin over factureren in de brief van een offerte komt uit hetzelfde gegeven, via de plaatshouder `{factureren}`. Na de eerste aanlevering ligt het ritme vast.

**Perioden zijn hele kalendermaanden.** Een kwartaal waarvan de opdracht maar een deel beslaat, is een periode van minder maanden. De eerste en de laatste periode kunnen dus korter zijn.

**Een aanlevering is een feit met een document.** Bij aanleveren bevriest grip de factuurgegevens van de maanden van de periode, zoals het dat per maand al deed, en groepeert ze in één aanlevering met een kenmerk (het kenmerk van de getekende offerte en de periode). Van de aanlevering maakt grip één keer een document, het factuurverzoek, in de huisstijl van de offerte. Het wordt bewaard; een later briefhoofd of tarief verandert het niet. Het factuurverzoek noemt het bedrag, aan wie de factuur gaat, de afspraak, en de specificatie per maand.

**De specificatie noemt rollen.** Een offerte noemt geen mensen, en wat eruit volgt ook niet: per maand staat er een regel per rol en tarief. Alleen als de factuurafspraken het zeggen, staat er een regel per persoon; dan vraagt het document ook het recht om tarieven van mensen te zien.

**Een wijziging achteraf reist mee.** Verandert de prijs van een maand die al is aangeleverd, dan ontstaat een naverrekening, zoals voorheen. Zij gaat mee met de eerstvolgende aanlevering en staat daar als eigen regel. Is er geen volgende periode meer, dan wordt de periode zelf opnieuw aanleverbaar voor alleen het verschil.

**Aanleveren zegt aan wie en hoe.** Kan de instantie mailen en is het adres van de financiële administratie ingesteld (`billing.recipient`), dan stuurt grip een bericht met een link naar het factuurverzoek achter de login. Het bericht heeft geen bijlage: mail is geen vertrouwelijk kanaal. Anders, of naar keuze, geeft de opdrachtmanager het document zelf door; dat wordt zo vastgelegd. Een download alleen is geen aanlevering.

**De factuur hoort bij de periode.** Wie vastlegt dat de factuur is verstuurd, doet dat voor de aangeleverde periode: nummer, datum en bedrag. Een verschil tussen aangeleverd en gefactureerd blijft zichtbaar.

**Eén bestand voor een systeem blijft.** De regels van een aanlevering zijn ook als csv te downloaden, in het formaat dat er al was. Er komt geen e-factuur: grip maakt geen facturen, en niemand heeft om een formaat gevraagd.

## Het scherm

Het tabblad heet "Afsluiten en factureren" en heeft drie lagen. Bovenaan staat het ene dat nu moet gebeuren, met het bedrag en de enige primaire knop. Daaronder staan de perioden als het verloop: per periode een regel met de stand, de laatste stap en het bedrag. Maanden en mensen komen op verzoek: de maanden van een periode klappen open, een maand opent in een paneel met één vraag ("Klopt dit met wat er in juli is gewerkt?"). Perioden die nog niet zijn begonnen, zijn één rustige regel.

De pagina Factureren toont hetzelfde over alle opdrachten die iemand beheert: wat klaarstaat gaat in één keer naar de financiële administratie.

## Gevolgen

- Nieuwe tabellen `billing_terms` en `billing_delivery`; een export krijgt een verwijzing naar zijn aanlevering (migratie `0032_billing_delivery`).
- Exports van voor deze wijziging hebben geen aanlevering. Hun maanden tellen als aangeleverd en hun factuur kan per periode worden vastgelegd; een document hebben ze niet.
- De oude routes per maand blijven bestaan.
- Het ritme wijzigen nadat een offerte is gemaakt, laat de brief en het systeem uiteenlopen. Grip houdt dat niet tegen.
- De bijlage Factuurinformatie van de offerte heeft lege vakken. De opdrachtgever vult ze in; de opdrachtmanager neemt ze één keer over bij de factuurafspraken.

## Wat niet is uitgezocht

Hoe onderdelen van de Rijksoverheid onderling verrekenen, is niet uit openbare bronnen nagegaan. Leveranciers van het Rijk factureren elektronisch (NLCIUS, UBL, via Peppol); of dat voor een verrekening tussen twee onderdelen van het Rijk geldt, of dat het een interne doorbelasting zonder factuur is, weet de financiële administratie. Vragen voor haar:

1. Is wat de organisatie stuurt een factuur, of een interne verrekening?
2. Welke gegevens zijn verplicht om er een te maken, en ontbreekt er iets op het factuurverzoek?
3. Wil zij de regels in een systeem inlezen, en zo ja in welk formaat?
4. Mag de specificatie rollen noemen, of vraagt de opdrachtgever namen?
5. Naar welk adres gaat het bericht dat er een factuurverzoek klaarstaat, en hebben de medewerkers daar een account in grip?
6. Kan zij het factuurnummer en de datum terugmelden, zodat niemand ze hoeft over te typen?
