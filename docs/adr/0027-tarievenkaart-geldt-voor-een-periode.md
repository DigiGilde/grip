# 0027 Een tarievenkaart geldt voor een periode, en de prijs volgt de dag

Status: aanvaard (2026-10-08). Vervangt het uitgangspunt "een tarievenkaart per kalenderjaar" uit de basisbeschrijving.

## Context

De basisbeschrijving ging uit van een tarievenkaart per kalenderjaar. Alles volgde daaruit: de kaart had het jaar als sleutel, een maand werd geprijsd met "de kaart van het jaar van die maand", een jaar kon worden gesloten, en een nieuw jaar begon als kopie van het vorige.

Zo werkt het niet. Tarieven gelden voor een periode. Vaak is dat een jaar, maar ze kunnen ook halverwege veranderen, op elke dag. Hetzelfde geldt voor mensen: iemand gaat halverwege het jaar een schaal omhoog, en het besluit daarover komt vaak later dan de dag waarop het ingaat.

Daarbij hoort een belofte: wij factureren wat het ons kost, altijd tegen het juiste tarief. Dat is meer dan "vanaf nu het nieuwe tarief". Als de prijs van een maand die al voorbij is verandert, moet het verschil alsnog worden verrekend.

## Besluit

**Een tarievenkaart geldt van een datum tot een datum.** Elke datum mag; een einddatum is optioneel. Een kaart heeft een eigen naam ("Tarieven 2026", "Tarieven vanaf 15 juli 2026"). Kaarten die prijzen (actief of gesloten) overlappen niet. Een concept prijst niets en mag de kaart overlappen die het gaat opvolgen. Tussen twee kaarten mag een gat zitten; een dag in dat gat prijzen is een fout, nooit nul.

**Een inzetschaal geldt net zo van een datum tot een datum.** De perioden van een persoon overlappen niet. Een schaal vastleggen vanaf een dag binnen een bestaande periode beeindigt die periode op de dag ervoor.

**De prijs volgt de dag.** Binnen een kalendermaand wordt de inzet gesplitst in de stukken waarin tarievenkaart en inzetschaal gelijk blijven. Elk stuk telt voor zijn aandeel in de maand, in kalenderdagen, tegen het maandtarief dat in dat stuk geldt. De stukken van een maand worden exact opgeteld en de maand wordt een keer afgerond. Een maand waarin niets verandert bestaat uit een stuk met precies het maanddeel van voorheen, en wordt dus berekend met dezelfde formule als altijd: bestaande totalen en de rekenvoorbeelden verschuiven niet.

**Een nieuwe kaart begint als concept**, als kopie van de kaart die vlak daarvoor geldt, met een verhoging en een afronding. Activeren beeindigt de vorige kaart op de dag ervoor, in dezelfde transactie; de auditregel van de activering zegt welke kaart is ingekort. Voor het activeren toont grip wat het doet: hoeveel begrotingsregels en hoeveel inzet een ander bedrag krijgen en met hoeveel in totaal.

**Gesloten is een eigenschap van de kaart.** Een wijziging in de periode van een gesloten kaart vraagt het recht beheerder en laat een auditregel achter. Wat buiten die periode valt is vrij.

**Een regel voor "de prijs van een voorbije maand is veranderd"**, wat de oorzaak ook is: een inzetschaal met een begindatum in het verleden, of een tarievenkaart die in het verleden ingaat. Beide zijn de waarheid en beide mogen.

- Een open maand prijst vanaf dat moment goed.
- Een afgesloten maand die nog niet is aangeleverd ook. Een afsluiting bewaart het vastgestelde percentage, nooit een bedrag. Verandert kaart of schaal binnen zo'n maand, dan geldt het vastgestelde percentage voor elk stuk van de maand.
- Een maand die al is aangeleverd houdt haar aanlevering zoals die was. Het verschil wordt een naverrekening: een eigen aanlevering met regels die naar de maand verwijzen en het verschil per inzet bevatten. Tot ze is aangeleverd telt ze als nog aan te leveren, en daarna als nog te factureren tot er een factuur op is vastgelegd. Een negatief verschil werkt hetzelfde.
- Voor het opslaan toont grip per opdracht welke afgesloten, aangeleverde en gefactureerde maanden worden geraakt en het verschil in euro.

Niets hoeft daarvoor de oorzaak te kennen: wat voor een maand nog aan te leveren is, is wat de maand nu kost min wat ervoor is aangeleverd.

**Wat een offerte beloofde.** Een begrotingsregel is begroot op een categorie en houdt die. Wie erop werkt declareert tegen het juiste tarief. Na een promotie loopt de regel dus over. Grip maakt dat zichtbaar en noemt de oorzaak ("gepromoveerd per 1 juli 2026: vanaf dan categorie C, de regel is begroot op B") voor wie mag zien wat iemand declareert, en als "tariefwijziging per 1 juli 2026" voor wie alleen het signaal mag zien. Er wordt niets geblokkeerd.

## Gevolgen

- De rekenmodule zoekt het tarief per dag. `RateBook.card`, `monthly_rate_cents` en `category_for_scale` nemen een dag (een maand of een kaal jaartal werkt nog en betekent de eerste dag ervan). Een maandbedrag kent zijn stukken.
- Subtotalen per kalenderjaar blijven bestaan als manier van tonen. Een declarabiliteitstarget blijft een afspraak per kalenderjaar; het bedrag telt de maandtarieven op, binnen een maand per dag.
- De strategieen voor gedeeltelijke maanden die er zijn om met Grist aan te sluiten (hele maanden, de DATEDIF-variant) blijven kiesbaar voor de import. De regel voor grip zelf is per dag.
- Een offerteregel draagt een tarief, of bij een wijziging binnen de periode de tarieven per geldigheidsperiode: begindatum, einddatum en maandtarief, waarbij een periode op elke dag kan beginnen en eindigen. Valt elke wijziging op 1 januari, dan blijft de bestaande vorm per jaar. Een uitgegeven offerte houdt de tarieven waarmee ze is uitgegeven.
- Twee gebeurtenissen: `person_scale.changed` en `billing_correction.arose`. De tweede is er voor de takenlaag: "lever de naverrekening aan".
- Bestaande kaarten zijn omgezet naar kaarten van 1 januari tot en met 31 december van hun jaar. Een jaartal in een adres of aanroep vindt nog de kaart die op 1 januari van dat jaar ingaat.
- Wat hiermee niet is geregeld: een deeltijdfactor per persoon, en beleid over wat een opdrachtgever na een promotie betaalt. Dat laatste is aan de organisatie; grip laat het verschil zien.
