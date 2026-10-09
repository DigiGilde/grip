# 0038 Een taak vertelt wat de lezer moet doen

Status: aanvaard (2026-10-08)

## Context

De takenlaag (ADR 0024) maakt en sluit taken uit feiten. Wat een lezer van een taak te zien kreeg, was de werking van die laag: een titel in de gebiedende wijs, voor wie de taak is, op wie ze wacht, een status, de zin "sluit vanzelf zodra", een link "ga naar het werk" en als enige knop het bewaren van een notitie.

Dat zegt niet wat de lezer nu moet doen. Een taak stond op naam van de aanvrager en wachtte tegelijk op "de controller", terwijl niemand voor dat advies was genoemd. De ene knop van het scherm was het minst belangrijke wat je met een taak kunt doen. Waarom de taak er was, stond er niet.

## Besluit

Een taak wordt aan haar lezer verteld, in deze volgorde:

1. wat je moet doen, in één zin aan jou; of, als het niet aan jou is: wie wat moet doen, en dat jij nu niets hoeft te doen;
2. waarover, als link naar de vacature of de opdracht zelf;
3. waarom nu: wat er gebeurde waardoor de taak er is;
4. vóór wanneer, en wat erna komt;
5. de ene handeling, als knop met de naam van de knop op de pagina waar het werk gebeurt.

Over hoe een taak sluit, zegt het scherm niets. Dat een taak door een feit sluit, blijft de regel van ADR 0024; de lezer hoeft het niet te weten om het werk te doen.

**De zinnen zijn gegevens, naast het plan.** Per sjabloon staat in `backend/grip/data/tasks/guidance.json`: de titel voor wie het werk doet, waar een ander op wacht, de zin voor de doener, de zin voor wie wacht, de naam van de handeling, de reden, wat erna komt, en de bestemming. Het bestand geldt voor elke versie van het plan. Een zaak houdt de versie van het plan waarmee ze begon; een betere zin moet ook een lopende zaak bereiken. Het bestand kan alleen namen gebruiken die `grip/tasks/telling.py` aanbiedt, en wordt anders geweigerd. Een test faalt op een sjabloon van welk plan ook zonder vermelding, en op een bestemming die geen pagina is.

**Een stand die grip herkent, verandert de zin.** Het plan weet niet of er voor een advies al iemand is genoemd, of die persoon een account heeft, en of een aanvraag compleet is. Grip weet het bij het lezen. Per sjabloon kan het bestand voor zo'n stand een andere titel, zin en handeling geven. Zo wordt "wacht op de controller" voor de aanvrager "noem wie het advies geeft", en voor wie het mag vastleggen "leg het advies vast".

**Te doen en wachten zijn gescheiden.** De pagina Taken heeft twee groepen. "Te doen" is wat jij nu moet doen. "Wacht op anderen" is wat van jou is en op een ander wacht, plus de taken van anderen op de opdrachten waarvan je eigenaar bent en de vacatures die je hebt aangevraagd. Het getal in de navigatie telt alleen de eerste groep.

**Een taak leidt naar het werk.** De naam van een taak die jij moet doen, brengt je naar de pagina waar dat gebeurt. Die pagina zegt in een balk bovenaan voor welke taak je er bent, en zegt het ook als het werk gedaan is. Een taak waarop je wacht, of die je met één besluit afrondt, opent als paneel om te lezen. Een notitie is daar het stille laatste onderdeel.

**Een naam alleen voor wie de zaak beheert.** In een zin staat de naam van een persoon alleen voor wie de zaak mag bewerken of de taak zelf moet doen. Anders staat er de rol.

**Niemand heeft het recht.** Wacht een taak op een recht in grip dat niemand heeft, dan zegt de taak dat, en wie het kan toekennen.

**Een plan kan lopende zaken overnemen.** ADR 0024 laat een zaak de versie van het plan houden waarmee ze begon. Dat blijft de regel. Een plan kan onder `replaces` oudere versies noemen waarvan het de lopende zaken overneemt, voor het geval dat de oude indeling van het werk fout was. Versie 2026.3 doet dat voor 2026.2: daar ontstond aanleveren per maand, ook bij een opdracht die per kwartaal wordt gefactureerd (ADR 0039). Bij de overgang vervalt een open taak die het nieuwe plan niet meer vraagt, en blijft een taak die beide vragen dezelfde.

## Gevolgen

- Wie een sjabloon aan het plan toevoegt, voegt een vermelding toe aan `guidance.json`. Zonder faalt de test.
- De naam van een handeling volgt de knop op de pagina. Verandert die knop, dan verandert de vermelding mee; daar is geen test voor.
- Een taak lezen kost een paar zoekvragen meer: de namen en data voor de zinnen worden bij het lezen opgehaald, niet bij de taak bewaard.
- Het veld `title` van een taak blijft de titel uit het plan. De schermen tonen `headline`.
- Het advies van iemand zonder account kan alleen een beheerder vastleggen. De taak van de aanvrager zegt dat. Of de aanvrager dat zelf zou moeten kunnen, is een vraag over toegang en hier niet beslist.

## Later gewijzigd (2026-10-09)

Aanleveren en de factuur vastleggen hangen sindsdien aan een factuurperiode en niet aan een maand (ADR 0039). Een naverrekening heeft een eigen taak (ADR 0047). Het verloop van een zaak en de zin over de volgende stap komen uit dezelfde bron als de taken (ADR 0044).
